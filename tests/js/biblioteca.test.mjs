// Biblioteca del editor (capa 4b, Task 6): lo puro que exporta biblioteca.js
// (qué se muestra en cada panel, la miniatura, los mensajes de una subida, qué
// falta preparar). La clase `Biblioteca` es DOM y no corre en Node; importar el
// módulo, sí (modulos_navegador.test.mjs prueba que no toca la página al cargar).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  aceptarPara, detalleAudio, duracionTexto, etiquetaMas, faltaPreparar, miniatura, mensajeSubida, mensajeTransicion, nombreDe,
  despuesDelToque, opcionesImagen, repartir, revisarArchivo, textoFotoAgregada, tipoDeArchivo,
  textosBiblioteca, transicionesBiblioteca, urlPieza,
} from "../../static/editor/biblioteca.js";
import * as op from "../../static/editor/operaciones.js";
import { docBase, DURACIONES } from "./doc_base.mjs";

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
  // capa 5b (R6 de la Tarea 6): una foto subida a mitad de la sesión pide su copia liviana con el mismo `preparar=`
  assert.equal(faltaPreparar({ tipo: "imagen" }), true);
  assert.equal(faltaPreparar({ tipo: "imagen", url_proxy: "https://r2/p.jpg" }), false);
  assert.equal(faltaPreparar(null), false);
});

test("urlPieza pone el id de la pieza en la plantilla de la ruta", () => {
  assert.equal(urlPieza("/cliente/acme/ediciones/biblioteca/pieza/__CF__", "cf_1"), "/cliente/acme/ediciones/biblioteca/pieza/cf_1");
  assert.equal(urlPieza("/x/__CF__", "a b"), "/x/a%20b");
});

test("los textos de muestra son los presets que agregarTexto conoce", () => {
  assert.deepEqual(textosBiblioteca().map((t) => [t.preset, t.nombre]),
    [["titulo", "Título"], ["subtitulo", "Subtítulo"], ["precio", "Precio"], ["llamado", "Llamado"]]);
  for (const t of textosBiblioteca()) assert.ok(op.agregarTexto(docBase(), 0, t.preset, {}).seleccion, t.preset);
});

test("las transiciones de la biblioteca son las del render, en su orden, con nombre y explicación", () => {
  assert.deepEqual(transicionesBiblioteca().map((t) => t.tipo), op.TRANSICIONES);
  assert.deepEqual(transicionesBiblioteca().map((t) => t.nombre), ["Corte", "Fundido", "Deslizar", "Zoom", "Fundido a negro"]);
  for (const t of transicionesBiblioteca()) assert.ok(t.descripcion.length > 5, t.tipo);
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
  // el 10 pasó los 5 min: ni se pregunta; la primera pregunta por cada uno pide prepararlo (fix final 11)
  assert.deepEqual(pedidos, ["/m?ids=8,9,11&preparar=8,9,11"]);
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
    _firma: Biblioteca.prototype._firma,
    pintadas: 0,
    _pintarListas() { this.pintadas += 1; },
  };
  await Biblioteca.prototype._revisarPiezas.call(falsa);
  assert.deepEqual(operadas, [["video", 5, "A", punto]]);
  assert.deepEqual(dichos, [["No se pudo preparar «B». Vuelve a intentar.", true]]);
  assert.deepEqual([...falsa.preparando.keys()], ["cfC"]);
  assert.equal(falsa.datos.piezas.length, 3);
  assert.equal(falsa.pintadas, 1);                        // cambió: se repinta una vez
  // fix final 4: la pregunta siguiente trae lo mismo (cfC sigue preparándose): nada se repinta
  await Biblioteca.prototype._revisarPiezas.call(falsa);
  assert.equal(falsa.pintadas, 1);
  assert.deepEqual([...falsa.preparando.keys()], ["cfC"]);
});

test("nombreDe: el logo del proyecto (origen «marca», el de insumos.logo) se llama «Logo»", () => {
  assert.equal(nombreDe({ tipo: "imagen", origen: "marca", nombre: null }), "Logo");
  assert.equal(nombreDe({ tipo: "imagen", origen: "marca", nombre: "logo.png" }), "logo.png");
  assert.equal(nombreDe({ tipo: "imagen", origen: "subida", nombre: null }), "Imagen");
  assert.equal(nombreDe({ tipo: "audio", origen: "musica" }), "Canción");
});

test("firmaListado: igual si nada cambió (aunque lleguen objetos nuevos), distinta si cambió algo que se ve", async () => {
  const { firmaListado } = await import("../../static/editor/biblioteca.js");
  const datos = () => ({ materiales: [video(4)], piezas: [{ cf_id: "cf1", nombre: "Pieza", material_id: null, preparando: true }] });
  const base = firmaListado({ carga: "lista", datos: datos(), preparando: ["cf1", "cf2"] });
  assert.equal(firmaListado({ carga: "lista", datos: datos(), preparando: ["cf2", "cf1"] }), base);
  const conProxy = datos();
  conProxy.materiales[0].url_proxy = "https://r2/v4_p.mp4";
  const lista = datos();
  lista.piezas[0] = { ...lista.piezas[0], material_id: 9, preparando: false };
  for (const otro of [
    { carga: "lista", datos: conProxy, preparando: ["cf1", "cf2"] },
    { carga: "lista", datos: lista, preparando: ["cf1", "cf2"] },
    { carga: "lista", datos: datos(), preparando: ["cf1"] },
    { carga: "error", datos: datos(), preparando: ["cf1", "cf2"] },
  ]) assert.notEqual(firmaListado(otro), base);
});

test("_operar: con la edición cambiada en otra pestaña, la biblioteca lo dice así (no «debajo del video»)", async () => {
  const { Biblioteca } = await import("../../static/editor/biblioteca.js");
  const { mensajeConflicto } = await import("../../static/editor/propiedades_modelo.js");
  for (const [conflicto, esperado] of [[true, mensajeConflicto()], [false, "No se pudo agregar: el aviso está debajo del video."]]) {
    const dichos = [];
    const falsa = {
      editor: { operar: () => false, doc: () => docBase(), info: () => ({}), tiempo: () => 0, seleccion: null,
                agregarMateriales: () => {}, enConflicto: () => conflicto },
      _decir: (t, error) => dichos.push([t, error]),
      _motivo: Biblioteca.prototype._motivo,
    };
    assert.equal(Biblioteca.prototype._operar.call(falsa, { tipo: "texto", preset: "titulo", nombre: "Título" }, null), false);
    assert.deepEqual(dichos, [[esperado, true]]);
  }
});

test("_revisarMateriales: la primera pregunta por un material pide prepararlo (una vez); las siguientes solo leen", async () => {
  const { Biblioteca } = await import("../../static/editor/biblioteca.js");
  const urls = [];
  const cancion = { id: 7, tipo: "audio", url: "c.mp3", duracion_ms: 60000, picos: null };
  const falsa = {
    urls: { materiales_por_id: "/m" },
    esperando: new Map([[7, Date.now()]]),
    datos: { materiales: [], piezas: [] },
    editor: { agregarMateriales: () => {} },
    _pedirJSON: async (url) => {
      urls.push(url);
      return { que: "json", j: { materiales: { 7: cancion } } };
    },
    _ponerMaterial: Biblioteca.prototype._ponerMaterial,
    _pintarListas: () => {},
  };
  await Biblioteca.prototype._revisarMateriales.call(falsa);
  await Biblioteca.prototype._revisarMateriales.call(falsa);
  falsa.esperando.set(8, Date.now());                            // llega otro: se pide preparar solo ese
  await Biblioteca.prototype._revisarMateriales.call(falsa);
  assert.deepEqual(urls, ["/m?ids=7&preparar=7", "/m?ids=7", "/m?ids=7,8&preparar=8"]);
});

// ---- Capa 4c (8/10): «Borrar» en la biblioteca ----
import { motivoNoBorrar, puedeBorrarse, quitarMaterial, urlBorrar } from "../../static/editor/biblioteca.js";

test("se borra lo subido y un video de Crear preparado; el logo, una voz o Mi música no", () => {
  assert.equal(puedeBorrarse(video(1)), true);
  assert.equal(puedeBorrarse(video(2, { origen: "crear" })), true);
  assert.equal(puedeBorrarse({ id: 3, tipo: "audio", origen: "subida" }), true);
  for (const origen of ["marca", "voz", "musica"]) assert.equal(puedeBorrarse({ id: 4, tipo: "imagen", origen }), false, origen);
  // arreglo 3: una canción subida a Mi música también es origen «subida», pero se borra solo en Crear
  assert.equal(puedeBorrarse({ id: 5, tipo: "audio", origen: "subida", mi_musica: true }), false);
  assert.equal(urlBorrar("/cliente/acme/ediciones/materiales/__ID__/borrar", 12), "/cliente/acme/ediciones/materiales/12/borrar");
});

test("lo que usa la edición abierta no se borra (aunque todavía no se haya guardado)", () => {
  const doc = docBase();                                   // usa los materiales 1 (clon) y 2 (voz)
  assert.match(motivoNoBorrar(video(1), doc), /en uso en esta edición/);
  assert.equal(motivoNoBorrar(video(7), doc), null);
  assert.match(motivoNoBorrar({ id: 8, tipo: "imagen", origen: "marca" }, doc), /no se borra desde aquí/);
});

test("quitarMaterial lo saca de la lista y suelta la pieza de Crear que lo tenía (se puede volver a preparar)", () => {
  const datos = { materiales: [video(1), video(2, { origen: "crear" })], piezas: [{ cf_id: "cf1", material_id: 2 }, { cf_id: "cf2", material_id: null }] };
  const out = quitarMaterial(datos, 2);
  assert.deepEqual(out.materiales.map((m) => m.id), [1]);
  assert.deepEqual(out.piezas, [{ cf_id: "cf1", material_id: null }, { cf_id: "cf2", material_id: null }]);
  assert.equal(datos.materiales.length, 2, "no toca lo de entrada");
});

// ---- Capa 5a (Task 8, fix round 1): grabaciones, voces con IA y locuciones ----

test("repartir: «Audio» lista también las grabaciones, las voces con IA y las locuciones de Crear › Audios", () => {
  const bib = {
    materiales: [
      { id: 1, tipo: "audio", origen: "grabacion", nombre: "Grabación 14:32", duracion_ms: 5000 },
      { id: 2, tipo: "audio", origen: "voz", nombre: "Hola, esto es una voz…", idioma: "es", duracion_ms: 3000 },
      { id: 3, tipo: "audio", origen: "voz", nombre: null, duracion_ms: 3000 },        // un bloque del guion: no
      { id: 4, tipo: "audio", origen: "locucion", nombre: "Promo de verano", idioma: "en", duracion_ms: 9000 },
      { id: 5, tipo: "audio", origen: "subida", nombre: "Risa" },
    ],
    piezas: [],
  };
  assert.deepEqual(repartir(bib).audios.map((m) => m.id), [1, 2, 4, 5]);
});

test("nombreDe y detalleAudio: su nombre; sin nombre, qué es", () => {
  assert.equal(nombreDe({ tipo: "audio", origen: "grabacion", nombre: "Grabación 09:00" }), "Grabación 09:00");
  assert.equal(nombreDe({ tipo: "audio", origen: "grabacion" }), "Grabación");
  assert.equal(nombreDe({ tipo: "audio", origen: "locucion" }), "Voz");
  assert.equal(nombreDe({ tipo: "audio", origen: "voz" }), "Voz");
  assert.equal(detalleAudio({ tipo: "audio", origen: "grabacion", duracion_ms: 65000 }), "1:05 · Grabación");
  assert.equal(detalleAudio({ tipo: "audio", origen: "voz", duracion_ms: 3000 }), "0:03 · Voz con IA");
  assert.equal(detalleAudio({ tipo: "audio", origen: "locucion", duracion_ms: 3000 }), "0:03 · Crear › Audios");
  assert.equal(detalleAudio({ tipo: "audio", origen: "musica", duracion_ms: 3000 }), "0:03 · Mi música");
  assert.equal(detalleAudio({ tipo: "audio", origen: "subida", mi_musica: true }), "Mi música");
  assert.equal(detalleAudio({ tipo: "audio", origen: "subida", duracion_ms: 3000 }), "0:03 · Subido");
  assert.equal(etiquetaMas({ tipo: "audio", origen: "grabacion" }, "Grabación 09:00"), "Agregar «Grabación 09:00» como voz desde el cabezal");
  assert.equal(etiquetaMas({ tipo: "audio", origen: "subida" }, "Risa"), "Agregar «Risa» como música desde el cabezal");
  // una grabación se borra desde aquí (el servidor ya lo permite); una voz o una locución no
  assert.equal(puedeBorrarse({ origen: "grabacion" }), true);
  assert.equal(puedeBorrarse({ origen: "voz" }), false);
  assert.equal(puedeBorrarse({ origen: "locucion" }), false);
});

// ---- Capa 5b (Tarea 8, D12): la imagen como clip o encima, y lo que se dice ----

test("opcionesImagen: «Como clip del video» primero y «Encima del video» después", () => {
  assert.deepEqual(opcionesImagen(), [
    { como: "clip", texto: "Como clip del video" },
    { como: "capa", texto: "Encima del video" },
  ]);
});

// Revisión final: en una edición de imagen (la principal no es un video) no
// hay «clip del video» que ofrecer — la imagen entra directo como capa.
test("opcionesImagen: sin pista principal de video, solo «Encima del video»", () => {
  const conVideo = { pistas: [{ id: "p_video", tipo: "video", clips: [] }] };
  assert.equal(opcionesImagen(conVideo).length, 2);
  const deImagen = { pistas: [{ id: "p_imagen", tipo: "imagen", clips: [{ id: "i0", inicio_ms: 0, duracion_ms: 1, material_id: 3 }] }] };
  assert.deepEqual(opcionesImagen(deImagen), [{ como: "capa", texto: "Encima del video" }]);
});

test("miniatura de una imagen: su copia liviana si ya la tiene; si no, el original", () => {
  const foto = { id: 3, tipo: "imagen", url: "https://r2/f.png", ancho: 600, alto: 400 };
  assert.equal(miniatura(foto).url, "https://r2/f.png");
  assert.equal(miniatura({ ...foto, url_proxy: "https://r2/f.proxy.jpg" }).url, "https://r2/f.proxy.jpg");
});

test("textoFotoAgregada dice cuánto dura la foto y dónde se cambia", () => {
  assert.equal(textoFotoAgregada(3000), "Foto agregada al video: dura 3 s. Cámbialo en «Editar».");
  assert.equal(textoFotoAgregada(2500), "Foto agregada al video: dura 2,5 s. Cámbialo en «Editar».");
});

test("mensajeTransicion: junta los dos clips (y dice cuánto se acortó); «Corte» a propósito no es un error", () => {
  const antes = docBase();
  const pedido = ["ponerTransicion", "v0", "fundido", 500];
  const despues = op.ponerTransicion(antes, "v0", "fundido", 500, DURACIONES).doc;
  assert.deepEqual(mensajeTransicion(antes, despues, pedido, { transicion: "fundido", nombre: "Fundido" }), {
    texto: "«Fundido» quedó en la unión: junta los dos clips y el video quedó 0,5 s más corto.", error: false,
  });
  // quitarla con «Corte» a propósito: lo de siempre, sin el aviso de «no hay video de sobra»
  const sinTr = op.ponerTransicion(despues, "v0", "corte", 500, DURACIONES).doc;
  assert.deepEqual(mensajeTransicion(despues, sinTr, ["ponerTransicion", "v0", "corte", 500], { transicion: "corte", nombre: "Corte" }),
    { texto: "Esa unión quedó en corte, sin transición.", error: false });
});

// Revisión final de la capa 5b: el repintado que esperaba a que se cerrara el
// menú de una imagen, si lo cerró un toque afuera, espera a que ese toque
// termine — si no, la lista nueva reemplazaba la tarjeta bajo el dedo y el
// toque (su click) no llegaba a nada.
function documentoFalso() {
  const oyentes = new Map();
  return {
    addEventListener(tipo, fn, captura) { oyentes.set(`${tipo}:${captura}`, fn); },
    removeEventListener(tipo, fn, captura) { if (oyentes.get(`${tipo}:${captura}`) === fn) oyentes.delete(`${tipo}:${captura}`); },
    soltar(tipo = "pointerup") { oyentes.get(`${tipo}:true`)?.({ type: tipo }); },
    oyentes,
  };
}
function relojFalso() {
  const pendientes = [];
  return { programar: (fn, ms) => pendientes.push({ fn, ms }), correr: () => pendientes.splice(0).forEach((p) => p.fn()), pendientes };
}

test("despuesDelToque: pinta después del click del toque que cerró el menú (pointerup + setTimeout 0), una sola vez", () => {
  const doc = documentoFalso();
  const reloj = relojFalso();
  let pintadas = 0;
  despuesDelToque(doc, () => pintadas++, reloj.programar);
  assert.equal(pintadas, 0, "nada mientras el dedo sigue abajo");
  doc.soltar();
  assert.equal(pintadas, 0, "ni en el pointerup: el click todavía no salió");
  assert.ok(reloj.pendientes.some((p) => p.ms === 0));
  reloj.correr();
  assert.equal(pintadas, 1);
  doc.soltar();
  reloj.correr();
  assert.equal(pintadas, 1, "una sola vez, y sin oyentes colgados");
  assert.equal(doc.oyentes.size, 0);
});

test("despuesDelToque: un toque cancelado (el dedo corrió la lista) también pinta", () => {
  const doc = documentoFalso();
  const reloj = relojFalso();
  let pintadas = 0;
  despuesDelToque(doc, () => pintadas++, reloj.programar);
  doc.soltar("pointercancel");
  reloj.correr();
  assert.equal(pintadas, 1);
});

// ---- Capa 5c (Tarea 8): la pestaña «Stickers», los emojis y las plantillas de «Texto» ----
import { mensajeSticker, urlSticker } from "../../static/editor/biblioteca.js";

test("urlSticker: la ruta de la biblioteca más /sticker/<id> (el id nunca arma otra ruta)", () => {
  assert.equal(urlSticker("/cliente/acme/ediciones/biblioteca", "estrella"), "/cliente/acme/ediciones/biblioteca/sticker/estrella");
  assert.equal(urlSticker("/b", "../x"), "/b/sticker/..%2Fx");
});

test("mensajeSticker: lo que el servidor dijo; si no, el número del error; sin red, «no hay conexión»; con la sesión vencida, eso", () => {
  assert.equal(mensajeSticker({ status: 404, cuerpo: { error: "Ese sticker no existe." } }), "No se pudo agregar el sticker (Ese sticker no existe).");
  assert.equal(mensajeSticker({ status: 500, cuerpo: null }), "No se pudo agregar el sticker (error 500).");
  assert.equal(mensajeSticker({ status: 502, cuerpo: { error: "" } }), "No se pudo agregar el sticker (error 502).");
  assert.equal(mensajeSticker({ red: true }), "No se pudo agregar el sticker (no hay conexión).");
  assert.equal(mensajeSticker({ redirigido: true, status: 200 }), "Tu sesión terminó: recarga la página e inicia sesión.");
});

const MATERIAL_ESTRELLA = { id: 21, tipo: "imagen", url: "https://r2/sticker_estrella.png", url_proxy: "https://r2/sticker_estrella.png",
  ancho: 512, alto: 512, tenible: true, origen: "sticker", nombre: "estrella" };
const ESTRELLA = { id: "estrella", categoria: "formas", archivo: "estrella.png", ancho: 512, alto: 512, color: "#FFD400", url: "/static/stickers/estrella.png" };

// Una respuesta de fetch (lo que biblioteca.js lee de ella).
const respuesta = ({ status = 200, json = null, redirected = false, html = false, url = "" } = {}) => ({
  ok: status >= 200 && status < 300, status, redirected, url,
  headers: { get: () => (html ? "text/html" : "application/json") },
  json: async () => {
    if (html || json === null) throw new SyntaxError("Unexpected token <");
    return json;
  },
});

// Una biblioteca de mentira para los métodos que no tocan el DOM: el editor anota lo que se le pide.
async function bibliotecaFalsa({ operar = () => true, tiempo = 2500 } = {}) {
  const { Biblioteca } = await import("../../static/editor/biblioteca.js");
  const operadas = [];
  const dichos = [];
  const agregados = [];
  const enfocados = [];
  const falsa = {
    urls: { biblioteca: "/cliente/acme/ediciones/biblioteca" },
    cosas: new Map(),
    editor: {
      doc: () => docBase(), tiempo: () => tiempo, seleccion: null, destino: () => "es_CO", info: () => ({}),
      agregarMateriales: (m) => agregados.push(Object.keys(m).map(Number)),
      operar: (...a) => { operadas.push(a); return operar(...a); },
      enfocarTexto: () => enfocados.push(true),
      enConflicto: () => false,
    },
    _decir: (texto, error = false) => dichos.push([texto, error]),
    _motivo: () => null,
    _esperar: () => { throw new Error("un sticker no espera ninguna copia liviana"); },
  };
  for (const m of ["_operar", "agregar", "_agregarSticker"]) falsa[m] = Biblioteca.prototype[m];
  return { falsa, operadas, dichos, agregados, enfocados };
}

async function conFetch(fn, fetchFalso) {
  const antes = globalThis.fetch;
  globalThis.fetch = fetchFalso;
  try {
    return await fn();
  } finally {
    if (antes === undefined) delete globalThis.fetch;
    else globalThis.fetch = antes;
  }
}

test("un sticker: POST a <biblioteca>/sticker/<id> y, con su material, una capa de imagen al 35 % del color del sticker (un deshacer)", async () => {
  const { falsa, operadas, dichos, agregados } = await bibliotecaFalsa();
  const pedidos = [];
  falsa.cosas.set("s:estrella", { tipo: "sticker", sticker: ESTRELLA, nombre: "Estrella" });
  const hecho = await conFetch(() => falsa.agregar("s:estrella"), async (url, opciones) => {
    pedidos.push([url, opciones]);
    return respuesta({ json: { material: MATERIAL_ESTRELLA } });
  });
  assert.equal(hecho, true);
  assert.deepEqual(pedidos, [["/cliente/acme/ediciones/biblioteca/sticker/estrella", {
    method: "POST", credentials: "same-origin", headers: { Accept: "application/json", "X-Requested-With": "fetch" },
  }]]);
  assert.deepEqual(agregados, [[21]], "el material entra a la vista previa ANTES de operar");
  assert.deepEqual(operadas, [["agregarImagen", MATERIAL_ESTRELLA, 2500, { fraccion: 0.35, tinte: "#FFD400" }]]);
  assert.deepEqual(dichos, [["Sticker agregado: cámbiale el color en «Editar».", false]]);
});

test("un sticker soltado en la línea de tiempo se agrega donde se soltó (después de pedirlo)", async () => {
  const { falsa, operadas } = await bibliotecaFalsa();
  falsa.cosas.set("s:estrella", { tipo: "sticker", sticker: ESTRELLA, nombre: "Estrella" });
  const punto = { pistaId: "p_texto", tipo: "texto", tMs: 3300, indicePrincipal: null };
  await conFetch(() => falsa.agregar("s:estrella", punto), async () => respuesta({ json: { material: MATERIAL_ESTRELLA } }));
  assert.deepEqual(operadas, [["agregarImagen", MATERIAL_ESTRELLA, 3300, { fraccion: 0.35, tinte: "#FFD400" }]]);
});

test("un sticker que el servidor no pudo dar: lo dice (con el motivo) y no toca la edición", async () => {
  const casos = [
    [async () => respuesta({ status: 404, json: { error: "Ese sticker no existe." } }), "No se pudo agregar el sticker (Ese sticker no existe)."],
    [async () => respuesta({ status: 403, json: { error: "Pedido rechazado: no viene de esta página." } }), "No se pudo agregar el sticker (Pedido rechazado: no viene de esta página)."],
    [async () => respuesta({ status: 500, html: true }), "No se pudo agregar el sticker (error 500)."],       // R2 falló: el cuerpo es HTML
    [async () => respuesta({ status: 200, json: {} }), "No se pudo agregar el sticker (error 200)."],       // sin `material`
    [async () => { throw new TypeError("Failed to fetch"); }, "No se pudo agregar el sticker (no hay conexión)."],
    // la sesión venció: llega la página de entrar (el servidor redirige a /login y fetch la sigue)
    [async () => respuesta({ status: 200, redirected: true, url: "https://app.test/login?next=%2Fcliente", html: true }),
      "Tu sesión terminó: recarga la página e inicia sesión."],
    [async () => respuesta({ status: 200, html: true }), "Tu sesión terminó: recarga la página e inicia sesión."],
  ];
  for (const [fetchFalso, esperado] of casos) {
    const { falsa, operadas, dichos, agregados } = await bibliotecaFalsa();
    falsa.cosas.set("s:estrella", { tipo: "sticker", sticker: ESTRELLA, nombre: "Estrella" });
    assert.equal(await conFetch(() => falsa.agregar("s:estrella"), fetchFalso), false, esperado);
    assert.deepEqual(dichos, [[esperado, true]]);
    assert.deepEqual([operadas, agregados], [[], []], esperado);
  }
});

test("un sticker se pide una vez a la vez: otro toque mientras el primero se pide no suma uno más", async () => {
  const { falsa, operadas } = await bibliotecaFalsa();
  falsa.cosas.set("s:estrella", { tipo: "sticker", sticker: ESTRELLA, nombre: "Estrella" });
  let pedidos = 0;
  let liberar;
  const espera = new Promise((r) => { liberar = r; });
  const fetchLento = async () => {
    pedidos += 1;
    await espera;
    return respuesta({ json: { material: MATERIAL_ESTRELLA } });
  };
  await conFetch(async () => {
    const primero = falsa.agregar("s:estrella");
    assert.equal(await falsa.agregar("s:estrella"), false, "el segundo toque no hace nada");
    liberar();
    assert.equal(await primero, true);
    // ya terminó: otro toque agrega otro sticker (cada toque, un deshacer)
    assert.equal(await falsa.agregar("s:estrella"), true);
  }, fetchLento);
  assert.equal(pedidos, 2);
  assert.equal(operadas.length, 2);
});

test("si la edición rechaza el sticker (cambió en otra pestaña), la biblioteca lo dice", async () => {
  const { falsa, dichos } = await bibliotecaFalsa({ operar: () => false });
  falsa.cosas.set("s:estrella", { tipo: "sticker", sticker: ESTRELLA, nombre: "Estrella" });
  const hecho = await conFetch(() => falsa.agregar("s:estrella"), async () => respuesta({ json: { material: MATERIAL_ESTRELLA } }));
  assert.equal(hecho, false);
  assert.deepEqual(dichos, [["No se pudo agregar: el aviso está debajo del video.", true]]);
});

test("un emoji: un texto con ese emoji solo en el cabezal, sin pedir foco para escribirlo", async () => {
  const { falsa, operadas, dichos, enfocados } = await bibliotecaFalsa();
  falsa.cosas.set("e:🔥", { tipo: "texto", preset: "emoji", literal: "🔥", nombre: "🔥" });
  assert.equal(falsa.agregar("e:🔥"), true);
  assert.deepEqual(operadas, [["agregarTexto", 2500, "emoji", { literal: "🔥" }]]);
  assert.deepEqual(dichos, [["Se agregó «🔥».", false]]);
  assert.deepEqual(enfocados, [], "un emoji no se escribe: el teclado no sube");
});

test("una plantilla para vender: un texto de ese preset en el cabezal, con su palabra elegida para escribir encima", async () => {
  const { falsa, operadas, dichos, enfocados } = await bibliotecaFalsa();
  falsa.cosas.set("t:oferta", { tipo: "texto", preset: "oferta", nombre: "OFERTA" });
  assert.equal(falsa.agregar("t:oferta"), true);
  assert.deepEqual(operadas, [["agregarTexto", 2500, "oferta", {}]]);
  assert.deepEqual(dichos, [["Texto agregado: escríbelo en «Editar».", false]]);
  assert.deepEqual(enfocados, [true]);
});

test("las plantillas y los emojis, por la página (vinculos.operar) nacen v2 con su preset: el pedido de la biblioteca es el que agregarTexto espera", () => {
  const { doc } = op.agregarTexto(docBase(), 2500, "oferta", {}, DURACIONES);
  const nuevo = doc.pistas.flatMap((p) => p.clips).find((c) => c.id.startsWith("oferta"));
  assert.equal(nuevo.texto.literal, "OFERTA");
  assert.equal(nuevo.estilo.version, 2);
  const emoji = op.agregarTexto(docBase(), 2500, "emoji", { literal: "🔥" }, DURACIONES).doc.pistas.flatMap((p) => p.clips).find((c) => c.id.startsWith("emoji"));
  assert.equal(emoji.texto.literal, "🔥");
  // sin el `{}` de opciones, `info` caería en su lugar: el pedido de una plantilla siempre lo lleva (escala.pedidoAgregar)
  assert.throws(() => op.agregarTexto(docBase(), 2500, "emoji", {}, DURACIONES), /Elige un emoji\./);
});
