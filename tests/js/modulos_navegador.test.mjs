// Los módulos de navegador no se pueden ejecutar en Node (usan el DOM al
// llamarlos), pero sí importarse: esto atrapa errores de sintaxis y de
// importación antes de abrir la página. Importarlos también prueba que no
// tocan `document` ni `window` al cargar (en Node no existen: la importación
// fallaría). vista.js y linea_tiempo.js ya no arrancan solos desde la capa 4a
// (lo hace pagina_editor.js, que sí lee la página al cargar y no se importa).
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

test("los módulos de navegador cargan y exportan lo que la página usa", async () => {
  assert.equal(typeof globalThis.document, "undefined");
  assert.equal(typeof globalThis.window, "undefined");
  const t = await import("../../static/editor/texto_canvas.js");
  const v = await import("../../static/editor/videos.js");
  const l = await import("../../static/editor/lienzo.js");
  const a = await import("../../static/editor/motor_audio.js");
  const vp = await import("../../static/editor/vista.js");
  const lt = await import("../../static/editor/linea_tiempo.js");
  const bib = await import("../../static/editor/biblioteca.js");
  const prop = await import("../../static/editor/propiedades.js");
  assert.equal(typeof t.rasterizarTexto, "function");
  assert.equal(typeof v.Videos, "function");
  assert.equal(typeof l.dibujarCuadro, "function");
  assert.equal(typeof a.MotorAudio, "function");
  assert.equal(typeof vp.VistaPrevia, "function");
  assert.equal(typeof lt.LineaTiempo, "function");
  for (const m of ["iniciar", "setDocumento", "tiempo", "ir", "pausar"]) {
    assert.equal(typeof vp.VistaPrevia.prototype[m], "function", `VistaPrevia.${m}`);
  }
  for (const g of ["materiales", "destino"]) {
    assert.equal(typeof Object.getOwnPropertyDescriptor(vp.VistaPrevia.prototype, g)?.get, "function", `VistaPrevia.${g}`);
  }
  // capa 4b (Task 5): la biblioteca pregunta qué hay bajo el dedo y resalta esa fila
  for (const m of ["dibujar", "moverCabezal", "puntoEn", "resaltar"]) {
    assert.equal(typeof lt.LineaTiempo.prototype[m], "function", `LineaTiempo.${m}`);
  }
  // capa 4b (Task 6): la biblioteca que construye pagina_editor.js
  assert.equal(typeof bib.Biblioteca, "function");
  for (const m of ["cargar", "agregar", "subir"]) {
    assert.equal(typeof bib.Biblioteca.prototype[m], "function", `Biblioteca.${m}`);
  }
  // capa 4b (Task 7): el panel de propiedades que construye pagina_editor.js
  assert.equal(typeof prop.Propiedades, "function");
  for (const m of ["pintar", "enfocarTexto"]) {
    assert.equal(typeof prop.Propiedades.prototype[m], "function", `Propiedades.${m}`);
  }
  // capa 4b (Task 8): tocar, mover y agrandar sobre el video; lo que le pide a la vista previa
  const li = await import("../../static/editor/lienzo_interaccion.js");
  assert.equal(typeof li.InteraccionLienzo, "function");
  for (const m of ["pintar", "destruir"]) {
    assert.equal(typeof li.InteraccionLienzo.prototype[m], "function", `InteraccionLienzo.${m}`);
  }
  assert.equal(typeof vp.VistaPrevia.prototype.medidasTexto, "function");
  assert.equal(typeof Object.getOwnPropertyDescriptor(vp.VistaPrevia.prototype, "resuelto")?.get, "function", "VistaPrevia.resuelto");
  // capa 5a (Task 7): la pestaña «Subtítulos» y dónde la monta la biblioteca
  const sub = await import("../../static/editor/subtitulos_panel.js");
  assert.equal(typeof sub.SubtitulosPanel, "function");
  for (const m of ["pintar", "generar", "seguir"]) {
    assert.equal(typeof sub.SubtitulosPanel.prototype[m], "function", `SubtitulosPanel.${m}`);
  }
  for (const m of ["zona", "mostrar"]) {
    assert.equal(typeof bib.Biblioteca.prototype[m], "function", `Biblioteca.${m}`);
  }
  // capa 5a (Task 8): la voz en off de la pestaña «Audio» (su parte pura y su panel)
  const vm = await import("../../static/editor/voz_modelo.js");
  for (const f of ["elegirGrabacion", "relojTexto", "motivoSinGrabar", "mensajeMicrofono", "estadoTexto", "filtrarVoces",
    "idiomaInicial", "botonCrear", "encargoVozGuardado"]) {
    assert.equal(typeof vm[f], "function", `voz_modelo.${f}`);
  }
  const voz = await import("../../static/editor/voz_panel.js");
  assert.equal(typeof voz.VozPanel, "function");
  for (const m of ["pintar", "crear", "seguir", "grabar", "parar", "usar", "descartar"]) {
    assert.equal(typeof voz.VozPanel.prototype[m], "function", `VozPanel.${m}`);
  }
  // capa 5b (Tarea 8): la biblioteca pregunta cómo entra una imagen y dice cómo quedó (lo puro)
  for (const f of ["opcionesImagen", "textoFotoAgregada", "mensajeTransicion", "faltaPreparar"]) {
    assert.equal(typeof bib[f], "function", `biblioteca.${f}`);
  }
  assert.equal(typeof globalThis.document, "undefined");          // importarlos no tocó la página
  const pps = Object.getOwnPropertyDescriptor(lt.LineaTiempo.prototype, "pps");
  assert.equal(typeof pps?.get, "function");
  assert.equal(typeof pps?.set, "function");
});

// ---- Capa 4b (Task 4): materiales que llegan sin recargar la página ----

test("VistaPrevia expone agregarMateriales y las ayudas puras que usa la página", async () => {
  const vp = await import("../../static/editor/vista.js");
  assert.equal(typeof vp.VistaPrevia.prototype.agregarMateriales, "function");
  assert.equal(typeof vp.VistaPrevia.prototype.renovarPendientes, "function");
  assert.equal(typeof vp.fusionarMateriales, "function");
  assert.equal(typeof vp.infoDe, "function");
});

test("fusionarMateriales suma sin tocar el mapa de antes y dice qué archivos cambiaron", async () => {
  const { fusionarMateriales } = await import("../../static/editor/vista.js");
  const antes = {
    1: { id: 1, tipo: "video", url: "https://r2/a.mp4", url_proxy: null, duracion_ms: 4000 },
    2: { id: 2, tipo: "audio", url: "https://r2/b.wav", url_proxy: null, picos: null },
    3: { id: 3, tipo: "imagen", url: "https://r2/c.png", url_proxy: null },
  };
  const copia = JSON.parse(JSON.stringify(antes));
  const r = fusionarMateriales(antes, {
    1: { ...antes[1], url_proxy: "https://r2/a_proxy.mp4" },       // llegó su copia liviana: cambia el archivo
    2: { ...antes[2], picos: [0.1, 0.4] },                          // solo los picos: el archivo es el mismo
    "7": { id: 7, tipo: "imagen", url: "https://r2/nueva.png" },     // nuevo
    8: null,                                                       // basura: se ignora
  });
  assert.deepEqual(antes, copia);                                   // el de antes no se toca
  assert.notEqual(r.materiales, antes);
  assert.deepEqual(Object.keys(r.materiales).sort(), ["1", "2", "3", "7"]);
  assert.equal(r.materiales[1].url_proxy, "https://r2/a_proxy.mp4");
  assert.deepEqual(r.materiales[2].picos, [0.1, 0.4]);
  assert.equal(r.materiales[3], antes[3]);
  assert.deepEqual(r.cambiados, [1, 7]);
  assert.deepEqual(r.recibidos, [1, 2, 7]);
  assert.deepEqual(fusionarMateriales(antes, {}).cambiados, []);
  assert.deepEqual(fusionarMateriales(antes, null).recibidos, []);
});

test("infoDe arma el mapa {id: {duracion_ms, tiene_audio, palabras}} que piden las operaciones", async () => {
  const { infoDe } = await import("../../static/editor/vista.js");
  const info = infoDe({
    1: { id: 1, tipo: "video", duracion_ms: 4000, tiene_audio: false },
    2: { id: 2, tipo: "audio", duracion_ms: 2000, tiene_audio: null, palabras: [{ t_ms: 0, dur_ms: 100, texto: "a" }] },
    3: { id: 3, tipo: "imagen", duracion_ms: null },
    4: { id: 4, tipo: "video", duracion_ms: 0 },                   // sin medir: desconocida, nunca 0
    5: null,
  });
  assert.deepEqual(info, {
    1: { duracion_ms: 4000, tiene_audio: false, palabras: null },
    2: { duracion_ms: 2000, tiene_audio: null, palabras: [{ t_ms: 0, dur_ms: 100, texto: "a" }] },
    3: { duracion_ms: null, tiene_audio: null, palabras: null },
    4: { duracion_ms: null, tiene_audio: null, palabras: null },
  });
  // las operaciones lo aceptan tal cual: agregar un video que dura 4 s
  const ops = await import("../../static/editor/operaciones.js");
  const { docBase } = await import("./doc_base.mjs");
  const res = ops.agregarVideo(docBase(), { id: 1 }, {}, info);
  assert.equal(res.doc.pistas[0].clips.at(-1).duracion_ms, 4000);
  assert.throws(() => ops.agregarVideo(docBase(), { id: 4 }, {}, info), /preparando/);
});

function vistaFalsa(VistaPrevia, llamadas, { reproduciendo = false } = {}) {
  return {
    reproduciendo,
    ocupado() { return this.reproduciendo; },
    renovarPendientes: VistaPrevia.prototype.renovarPendientes,
    porRenovar: new Set(),
    materialesVigentes: {
      1: { id: 1, tipo: "video", url: "https://r2/a.mp4", url_proxy: null },
      3: { id: 3, tipo: "imagen", url: "https://r2/c.png", url_proxy: null },
    },
    videos: { materiales: null, renovar: (mats, ids) => llamadas.push(["renovar", Object.keys(mats).sort(), ids]) },
    audio: { materiales: null, buffers: new Map([[1, "buf"], [9, "otro"]]), fallidos: new Set([1]) },
    imagenes: new Map([[3, { src: "https://r2/c.png" }]]),
    imagenesFallidas: new Set([3]),
    // D13 (capa 5b, Tarea 4): la caché aparte de la copia liviana (fotos de
    // la principal y la imagen principal) también se suelta al renovar.
    imagenesLigeras: new Map([[3, { src: "https://r2/c_p.png" }]]),
    imagenesLigerasFallidas: new Set([3]),
    // capa 5c (D11): los lienzos teñidos (un sticker del color elegido) también se sueltan
    imagenesTenidas: new Map([["3:#FFD400", {}], ["30:#FFD400", {}]]),
    fallasCarga: new Set([1, 3, 9]),
    mostrarFallas: () => llamadas.push(["fallas"]),
    pedirCuadro: () => llamadas.push(["cuadro"]),
    alCambiarMateriales: (m) => llamadas.push(["pagina", Object.keys(m).sort()]),
  };
}

const LLEGAN = {
  1: { id: 1, tipo: "video", url: "https://r2/a.mp4", url_proxy: "https://r2/a_p.mp4" },   // su copia liviana
  3: { id: 3, tipo: "imagen", url: "https://r2/c2.png", url_proxy: null },                // otra URL
  5: { id: 5, tipo: "audio", url: "https://r2/e.wav" },                                   // nuevo
};

test("agregarMateriales renueva los videos que cambiaron, avisa a la página y pide un cuadro", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const llamadas = [];
  const falsa = vistaFalsa(VistaPrevia, llamadas);
  const r = VistaPrevia.prototype.agregarMateriales.call(falsa, LLEGAN);
  assert.deepEqual(r, [1, 3, 5]);
  assert.deepEqual(Object.keys(falsa.materialesVigentes).sort(), ["1", "3", "5"]);
  assert.equal(falsa.audio.materiales, falsa.materialesVigentes);       // el sonido ve los nuevos
  assert.equal(falsa.videos.materiales, falsa.materialesVigentes);
  assert.equal(falsa.audio.buffers.has(1), false);                      // su archivo cambió: se vuelve a pedir
  assert.equal(falsa.audio.buffers.get(9), "otro");
  assert.equal(falsa.audio.fallidos.has(1), false);
  assert.equal(falsa.imagenes.has(3), false);                           // la imagen se vuelve a cargar
  assert.equal(falsa.imagenesFallidas.has(3), false);
  assert.equal(falsa.imagenesLigeras.has(3), false);                    // su copia liviana también
  assert.equal(falsa.imagenesLigerasFallidas.has(3), false);
  assert.deepEqual([...falsa.imagenesTenidas.keys()], ["30:#FFD400"]);   // el sticker teñido de ese material (no el «30:»)
  assert.deepEqual([...falsa.fallasCarga], [9]);
  assert.equal(falsa.porRenovar.size, 0);
  assert.deepEqual(llamadas, [
    ["renovar", ["1", "3", "5"], [1, 3, 5]],
    ["fallas"],
    ["cuadro"],
    ["pagina", ["1", "3", "5"]],
  ]);
  // nada nuevo: no avisa ni redibuja
  llamadas.length = 0;
  assert.deepEqual(VistaPrevia.prototype.agregarMateriales.call(falsa, {}), []);
  assert.deepEqual(llamadas, []);
});

test("agregarMateriales no corta lo que reproduce: recarga los archivos nuevos al pausar", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const llamadas = [];
  const falsa = vistaFalsa(VistaPrevia, llamadas, { reproduciendo: true });
  assert.deepEqual(VistaPrevia.prototype.agregarMateriales.call(falsa, LLEGAN), [1, 3, 5]);
  assert.deepEqual(Object.keys(falsa.materialesVigentes).sort(), ["1", "3", "5"]);   // ya entraron
  assert.equal(falsa.videos.materiales, falsa.materialesVigentes);                    // un clip nuevo ya los encuentra
  assert.equal(falsa.imagenes.has(3), true);                                          // lo que se ve sigue
  assert.equal(falsa.imagenesLigeras.has(3), true);
  assert.equal(falsa.imagenesTenidas.has("3:#FFD400"), true);
  assert.equal(falsa.audio.buffers.has(1), true);
  assert.deepEqual(llamadas, [["cuadro"], ["pagina", ["1", "3", "5"]]]);
  llamadas.length = 0;
  falsa.reproduciendo = false;
  falsa.renovarPendientes();                                                          // lo llama pausar()
  assert.deepEqual(llamadas, [["renovar", ["1", "3", "5"], [1, 3, 5]], ["fallas"]]);
  assert.equal(falsa.imagenes.has(3), false);
  assert.equal(falsa.imagenesLigeras.has(3), false);
  assert.equal(falsa.imagenesTenidas.has("3:#FFD400"), false);
  assert.equal(falsa.audio.buffers.has(1), false);
  llamadas.length = 0;
  falsa.renovarPendientes();                                                          // una sola vez
  assert.deepEqual(llamadas, []);
});

// ---- Capa 5b (Tarea 6, D13): usarListos (el sondeo de edicion_proxy) también
// suelta la copia liviana de una imagen que acaba de llegar, no solo
// videos.renovar — si no, una <Image> ya cacheada con el original (sin
// url_proxy) se queda con ese `src` para siempre.

test("usarListos suelta la copia liviana de las imágenes cuyo proxy llegó", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const llamadas = [];
  const falsa = {
    datos: { pendientes: [3, 9] },
    materialesVigentes: {
      1: { id: 1, tipo: "video", url: "https://r2/a.mp4", url_proxy: null },
      3: { id: 3, tipo: "imagen", url: "https://r2/c.png", url_proxy: null },
    },
    get materiales() { return this.materialesVigentes; },
    audio: { materiales: null },
    videos: { renovar: (mats, ids) => llamadas.push(["renovar", ids]) },
    fallasCarga: new Set([1, 3, 9]),
    imagenesLigeras: new Map([[3, { src: "https://r2/c.png" }]]),
    imagenesLigerasFallidas: new Set([3]),
    mostrarFallas: () => llamadas.push(["fallas"]),
    pedirCuadro: () => llamadas.push(["cuadro"]),
    alCambiarMateriales: (m) => llamadas.push(["pagina", Object.keys(m).sort()]),
  };
  const j = {
    pendientes: [9],                          // 9 sigue pendiente; 3 ya llegó
    materiales: { 3: { id: 3, tipo: "imagen", url: "https://r2/c.png", url_proxy: "https://r2/c_p.png" } },
  };
  VistaPrevia.prototype.usarListos.call(falsa, j);
  assert.deepEqual(falsa.datos.pendientes, [9]);
  assert.equal(falsa.materialesVigentes[3].url_proxy, "https://r2/c_p.png");
  assert.equal(falsa.imagenesLigeras.has(3), false);     // la caché vieja (sin proxy) se suelta
  assert.equal(falsa.imagenesLigerasFallidas.has(3), false);
  assert.deepEqual(llamadas, [["renovar", [3]], ["fallas"], ["cuadro"], ["pagina", ["1", "3"]]]);
});

// ---- Capa 4b (Task 8): las medidas de los textos para tocar sobre el video ----

test("medidasTexto mide solo los textos que se ven en ese instante, como los dibuja el lienzo", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const { docBase } = await import("./doc_base.mjs");
  const doc = docBase();
  doc.pistas[1].clips.push({ ...structuredClone(doc.pistas[1].clips[0]), id: "t2", inicio_ms: 5000, texto: { literal: "Chao" } });
  doc.pistas.push({ id: "p_texto2", tipo: "texto", oculta: true, clips: [{ ...structuredClone(doc.pistas[1].clips[0]), id: "t3" }] });
  const pedidos = [];
  const rasterizar = (literal, estilo, formato) => {
    pedidos.push([literal, estilo, formato]);
    return { ancho: 10 * literal.length, alto: 7 };
  };
  const falsa = { doc, tiempo: () => 1500 };
  assert.deepEqual(VistaPrevia.prototype.medidasTexto.call(falsa, 1500, rasterizar), { t1: [40, 7] });
  assert.deepEqual(pedidos, [["Hola", { fuente: "Inter-Bold" }, "9:16"]]);       // lo mismo que pide lienzo.js
  assert.deepEqual(VistaPrevia.prototype.medidasTexto.call(falsa, 5500, rasterizar), { t2: [40, 7] });
  assert.deepEqual(VistaPrevia.prototype.medidasTexto.call(falsa, undefined, rasterizar), { t1: [40, 7] });   // el cabezal
  delete doc.pistas[1].clips[0].texto.literal;                                    // sin texto no se dibuja
  assert.deepEqual(VistaPrevia.prototype.medidasTexto.call(falsa, 1500, rasterizar), {});
  assert.deepEqual(VistaPrevia.prototype.medidasTexto.call({ doc: null, tiempo: () => 0 }, 0, rasterizar), {});
  const resuelto = Object.getOwnPropertyDescriptor(VistaPrevia.prototype, "resuelto").get;
  assert.equal(resuelto.call({ doc }), doc);
});

// ---- Fixes finales de la capa 4b ----

test("fusionarMateriales: una copia vieja (de la biblioteca) sin copia liviana, tira ni picos no le quita a la vista los suyos", async () => {
  const { fusionarMateriales } = await import("../../static/editor/vista.js");
  const antes = {
    1: { id: 1, tipo: "video", url: "https://r2/a.mp4", url_proxy: "https://r2/a_p.mp4", proxy_version: 2,
         tira_url: "https://r2/a_t.jpg", duracion_ms: 4000, nombre: "Clip" },
    2: { id: 2, tipo: "audio", url: "https://r2/b.wav", url_proxy: null, picos: [0.1, 0.5], duracion_ms: 2000 },
  };
  const r = fusionarMateriales(antes, {
    1: { ...antes[1], url_proxy: null, proxy_version: null, tira_url: null, nombre: "Clip nuevo" },
    2: { ...antes[2], picos: null },
  });
  assert.equal(r.materiales[1].url_proxy, "https://r2/a_p.mp4");
  assert.equal(r.materiales[1].proxy_version, 2);
  assert.equal(r.materiales[1].tira_url, "https://r2/a_t.jpg");
  assert.equal(r.materiales[1].nombre, "Clip nuevo");          // lo demás sí se actualiza
  assert.deepEqual(r.materiales[2].picos, [0.1, 0.5]);
  assert.deepEqual(r.cambiados, []);                           // ningún archivo cambió: nada se recarga
  assert.deepEqual(r.recibidos, [1, 2]);
});

// ---- Subtítulos derivados (D1-D4, capa 5a): las palabras del material ----

test("fusionarMateriales: una copia sin palabras/tiene_palabras no le quita a la vista las que ya tenía", async () => {
  const { fusionarMateriales } = await import("../../static/editor/vista.js");
  const antes = {
    2: { id: 2, tipo: "audio", url: "https://r2/b.wav", palabras: [{ t_ms: 0, dur_ms: 300, texto: "voz" }], tiene_palabras: true },
  };
  const r = fusionarMateriales(antes, { 2: { ...antes[2], palabras: null, tiene_palabras: null } });
  assert.deepEqual(r.materiales[2].palabras, [{ t_ms: 0, dur_ms: 300, texto: "voz" }]);
  assert.equal(r.materiales[2].tiene_palabras, true);
  // y si SÍ llegan palabras nuevas (la transcripción terminó), se usan:
  const r2 = fusionarMateriales(antes, { 2: { ...antes[2], palabras: [{ t_ms: 0, dur_ms: 100, texto: "ya" }] } });
  assert.deepEqual(r2.materiales[2].palabras, [{ t_ms: 0, dur_ms: 100, texto: "ya" }]);
});

test("agregarMateriales rederiva los subtítulos del destino vigente cuando llegan palabras nuevas (D1)", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const llamadas = [];
  const clipBase = { inicio_ms: 0, duracion_ms: 1000, recorte: { desde_ms: 0, hasta_ms: 1000 }, velocidad: 1.0 };
  const docResuelto = {
    destino: { idioma: "es", pais: "CO" },
    subtitulos: { fuentes: { es: [{ tipo: "material", material_id: 9 }] }, palabras: [] },
    pistas: [
      { id: "p_video", tipo: "video", oculta: false, silenciada: false, clips: [{ ...clipBase, id: "v0", material_id: 1 }] },
      { id: "p_audio", tipo: "audio", oculta: false, silenciada: false, clips: [{ ...clipBase, id: "c1", material_id: 9 }] },
    ],
  };
  const falsa = vistaFalsa(VistaPrevia, llamadas);
  falsa.doc = docResuelto;
  const docAntes = falsa.doc;
  VistaPrevia.prototype.agregarMateriales.call(falsa, { 9: { id: 9, tipo: "audio", url: "https://r2/voz.wav", palabras: [{ t_ms: 0, dur_ms: 500, texto: "hola" }] } });
  assert.notEqual(falsa.doc, docAntes);                              // aplicarFuentes siempre devuelve uno nuevo
  assert.deepEqual(falsa.doc.subtitulos.palabras, [{ t_ms: 0, dur_ms: 500, texto: "hola" }]);
});

test("agregarMateriales no toca nada si todavía no hay destino resuelto (this.doc nulo)", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const llamadas = [];
  const falsa = vistaFalsa(VistaPrevia, llamadas);
  falsa.doc = null;
  assert.doesNotThrow(() => VistaPrevia.prototype.agregarMateriales.call(falsa, { 9: { id: 9, tipo: "audio", url: "x" } }));
  assert.equal(falsa.doc, null);
});

// ---- Capa 5b (Tarea 7, D6/D8): las medidas del cuadro de un clip de la
// principal, para mover y acercar su encuadre sobre el video ----

test("medidasPrincipal: las del cuadro que se dibuja (ya derecho); si no cargó, las del material", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const { docBase } = await import("./doc_base.mjs");
  const doc = docBase();
  doc.pistas[0].clips.push({ id: "f0", inicio_ms: 8000, duracion_ms: 3000, material_id: 4, foto: true,
    recorte: { desde_ms: 0, hasta_ms: 3000 }, velocidad: 1 });
  const ligera = { complete: true, naturalWidth: 300, naturalHeight: 200 };
  const falsa = {
    doc,
    documentoOriginal: doc,
    materialesVigentes: { 1: { tipo: "video", ancho: 1920, alto: 1080 }, 4: { tipo: "imagen", ancho: 600, alto: 400 } },
    // el <video> de v0 ya cargó (un video grabado de pie: el navegador lo da derecho); el de v1 no existe
    videos: { elementoDe: (clip) => (clip.id === "v0" ? { videoWidth: 720, videoHeight: 1280 } : null) },
    imagenesLigeras: new Map([[4, ligera]]),
  };
  const medidas = (id) => VistaPrevia.prototype.medidasPrincipal.call(falsa, id);
  assert.deepEqual(medidas("v0"), [720, 1280]);
  assert.deepEqual(medidas("v1"), [1920, 1080]);           // sin <video> todavía: el material
  assert.deepEqual(medidas("f0"), [300, 200]);             // la foto: su copia liviana (misma proporción)
  ligera.complete = false;
  assert.deepEqual(medidas("f0"), [600, 400]);             // todavía cargando: el material
  assert.equal(medidas("t1"), null);                       // un texto no es de la principal
  assert.equal(medidas("nada"), null);
  falsa.videos = { elementoDe: () => ({ videoWidth: 0, videoHeight: 0 }) };     // sin metadatos aún
  assert.deepEqual(medidas("v0"), [1920, 1080]);
  falsa.materialesVigentes = {};
  assert.equal(medidas("v0"), null);                       // nada que medir
  falsa.doc = null;                                        // antes de resolver el destino: el documento de la página
  falsa.materialesVigentes = { 1: { tipo: "video", ancho: 1280, alto: 720 } };
  assert.deepEqual(medidas("v1"), [1280, 720]);
});

// InteraccionLienzo es DOM, pero sus pasos se prueban con un `this` falso:
// arrastrar el video pide el encuadre con la clave "<clip>:encuadre" (UN
// deshacer por arrastre) y la caja del clip de la principal elegido es la
// parte del cuadro que se ve.
function elFalso() {
  const clases = new Set();
  return { hidden: true, style: {}, clases, classList: { toggle: (c, si) => (si ? clases.add(c) : clases.delete(c)) } };
}

test("InteraccionLienzo: arrastrar el video opera el encuadre con su clave; el asa, el zoom", async () => {
  const { InteraccionLienzo } = await import("../../static/editor/lienzo_interaccion.js");
  const llamadas = [];
  const guias = [];
  const falsa = {
    lienzo: { width: 1080, height: 1920 },
    _medida: () => ({ rect: { left: 0, top: 0, width: 270, height: 480 }, proporcion: 4 }),
    _guias: (g) => guias.push(g),
    _terminar: () => llamadas.push(["terminar"]),
    editor: { operarCon: (...a) => { llamadas.push(a); return true; } },
    gesto: {
      activo: true, tipo: "encuadre", id: "v0", formato: "9:16", inicio: { x: 540, y: 300 }, iman: 32,
      encuadre: { modo: "llenar", zoom: 1, x: 0.5, y: 0.5 }, medidas: [400, 200], x: 204, y: 75,  // (816, 300): +276 px del lienzo
    },
  };
  InteraccionLienzo.prototype._aplicar.call(falsa);
  assert.deepEqual(llamadas, [[{ clave: "v0:encuadre" }, "cambiar", "v0", { encuadre: { x: 0.4, y: 0.5 } }]]);
  assert.deepEqual(guias, [{ vertical: false, horizontal: false }]);
  // el asa: el zoom, con la misma clave y sin guías
  llamadas.length = 0;
  guias.length = 0;
  falsa.gesto = { ...falsa.gesto, tipo: "asa_encuadre", inicio: { x: 1072, y: 1912 }, asa: { x: 1072, y: 1912, sx: 1, sy: 1 },
    x: 268 + 133, y: 478 + 238 };                                                                // +532, +952
  InteraccionLienzo.prototype._aplicar.call(falsa);
  assert.deepEqual(llamadas, [[{ clave: "v0:encuadre" }, "cambiar", "v0", { encuadre: { zoom: 2 } }]]);
  assert.deepEqual(guias, [null]);
  // sin medidas del cuadro: no opera (ni corta el gesto)
  llamadas.length = 0;
  falsa.gesto = { ...falsa.gesto, tipo: "encuadre", medidas: null };
  InteraccionLienzo.prototype._aplicar.call(falsa);
  assert.deepEqual(llamadas, []);
  // una capa sigue con su clave de siempre
  falsa.gesto = { activo: true, tipo: "caja", id: "t1", formato: "9:16", inicio: { x: 540, y: 960 }, iman: 32,
    transform: { x: 0.5, y: 0.5 }, x: 135 + 25, y: 240 };
  InteraccionLienzo.prototype._aplicar.call(falsa);
  assert.deepEqual(llamadas[0].slice(0, 3), [{ clave: "t1:transform" }, "cambiar", "t1"]);
});

test("InteraccionLienzo: elegido el clip de la principal, su caja es lo que se ve y su asa la esquina", async () => {
  const { InteraccionLienzo } = await import("../../static/editor/lienzo_interaccion.js");
  const { docBase } = await import("./doc_base.mjs");
  const doc = docBase();
  doc.pistas[0].clips[0].encuadre = { modo: "ajustar", zoom: 1, x: 0.5, y: 0.5 };
  const falsa = {
    caja: elFalso(), asa: elFalso(),
    vista: { resuelto: doc, tiempo: () => 500, materiales: {}, medidasTexto: () => ({}) },
    editor: { seleccion: "v0" },
    medidasPrincipal: () => [400, 200],
    _medida: () => ({ rect: { width: 270, height: 480 }, proporcion: 4 }),
  };
  InteraccionLienzo.prototype.pintar.call(falsa);
  assert.equal(falsa.caja.hidden, false);
  assert.deepEqual(falsa.caja.style, { left: "0%", top: "35.9375%", width: "100%", height: "28.125%" });   // 0, 690, 1080×540
  assert.equal(falsa.caja.clases.has("ed-encuadre-caja"), true);
  assert.equal(falsa.asa.clases.has("ed-encuadre-asa"), true);
  assert.equal(falsa.asa.style.top, `${(1230 / 1920) * 100}%`);
  // una capa elegida: la caja de siempre, sin la marca del encuadre
  falsa.editor.seleccion = "a1";                                       // un audio: nada que mostrar
  InteraccionLienzo.prototype.pintar.call(falsa);
  assert.equal(falsa.caja.hidden, true);
  assert.equal(falsa.caja.clases.has("ed-encuadre-caja"), false);
  // sin quien mida (una vista sin medidasPrincipal): el video no tiene caja
  falsa.editor.seleccion = "v0";
  falsa.medidasPrincipal = null;
  InteraccionLienzo.prototype.pintar.call(falsa);
  assert.equal(falsa.caja.hidden, true);
});

test("Propiedades arma la foto y el bloque «Encuadre» (y la vista expone medidasPrincipal)", async () => {
  const prop = await import("../../static/editor/propiedades.js");
  for (const m of ["_armarFoto", "_armarEncuadre", "_armarZoomLento"]) {
    assert.equal(typeof prop.Propiedades.prototype[m], "function", `Propiedades.${m}`);
  }
  const vp = await import("../../static/editor/vista.js");
  assert.equal(typeof vp.VistaPrevia.prototype.medidasPrincipal, "function");
});

// ---- Capa 5b (Tarea 8): pagina_editor.js sin ejecutarla ----
// pagina_editor.js lee la página al cargarse (no se importa en Node): se mira
// sin correrla — su sintaxis (`node --check`) y que cada nombre que importa
// exista en su módulo (esos sí se importan, sin tocar la página). Así un
// nombre mal escrito (o «Vincular» enganchado a una función que no existe) se
// ve aquí y no al abrir el editor.
test("pagina_editor.js: compila y todo lo que importa existe (vinculos.operarGesto envuelve cada operación)", async () => {
  const ruta = new URL("../../static/editor/pagina_editor.js", import.meta.url);
  execFileSync(process.execPath, ["--check", fileURLToPath(ruta)]);          // lanza si no compila
  const fuente = readFileSync(ruta, "utf-8");
  const importaciones = [...fuente.matchAll(/^import\s+(\*\s+as\s+\w+|\{[^}]*\})\s+from\s+"(\.\/[\w.]+)";/gm)];
  assert.ok(importaciones.length >= 15, "se leyeron las importaciones");
  for (const [, que, de] of importaciones) {
    const modulo = await import(new URL(de, ruta).href);
    if (que.startsWith("*")) continue;
    for (const nombre of que.slice(1, -1).split(",").map((x) => x.trim().split(/\s+as\s+/)[0]).filter(Boolean)) {
      assert.ok(nombre in modulo, `${de} no exporta ${nombre}`);
    }
  }
  assert.match(fuente, /^import \* as vinculos from "\.\/vinculos\.js";$/m);
  const vinculos = await import("../../static/editor/vinculos.js");
  for (const f of ["operar", "operarGesto", "leerVincular", "guardarVincular"]) assert.equal(typeof vinculos[f], "function", `vinculos.${f}`);
  for (const uso of [
    // revisión final de la capa 5b: un gesto con clave se deriva de su base
    "vinculos.operarGesto(operaciones[nombre], historial.actual, args, info(),",
    "{ vincular, clave, gesto, continua: historial.fusionaria(clave) }",
    // revisión final: en el celular nadie ve el `title` — al tocar
    // «Vincular» se dice, breve y sin el rojo de un error
    'aviso(t(vincular ? "editar.vincular_si" : "editar.vincular_no"), { error: false, breve: true });',
    'n.classList.toggle("error", error);',
    "let vincular = vinculos.leerVincular(almacenSeguro());",
    "vinculos.guardarVincular(almacenSeguro(), vincular)",
    'pintarAvisoCarga("aviso-voces", a.voces)',
  ]) assert.ok(fuente.includes(uso), uso);
  // ninguna otra llamada directa a una operación: todas pasan por vinculos.operarGesto (un paso, un guardado)
  assert.doesNotMatch(fuente, /operaciones\[nombre\]\(historial\.actual/);
  assert.equal(typeof globalThis.document, "undefined");
});

// ---- Capa 5c (Tarea 4): fuentes que se bajan cuando hacen falta y stickers teñidos ----

const TABLA_5C = JSON.parse(readFileSync(new URL("../../static/editor/tipografia.json", import.meta.url), "utf8"));
const T0 = { ...TABLA_5C, emoji: null };
const T_E = { ...T0, emoji: { id: "E", upem: 1000, asc: 900, desc: 200,
  avances: [[0x2764, [1000]], [0x1F44D, [1000]], [0x1F468, [1000]], [0x1F525, [1000]]] } };

// Un documento con solo pistas de texto (y lo que cada prueba le suma).
const textoClip = (id, literalOVariable, estilo) => ({
  id, inicio_ms: 0, duracion_ms: 1000, texto: literalOVariable, estilo, transform: {}, keyframes: [], animacion: null,
});
const docDeTextos = (clips, extra = {}) => ({
  esquema: 1, formato: "9:16", pistas: [{ id: "p_texto", tipo: "texto", clips }], variables: { textos: {}, precios: {} }, ...extra,
});
const V2 = { version: 2, color: "#FFFFFF", tamano: 0.05 };

test("fuentesDelDocumento: las fuentes de los textos y la de emojis si un texto v2 lleva un emoji", async () => {
  const { fuentesDelDocumento } = await import("../../static/editor/vista.js");
  const doc = docDeTextos([
    textoClip("t1", { literal: "OFERTA" }, { fuente: "Anton-Regular" }),
    textoClip("t2", { variable: "hook" }, { fuente: "Inter-Bold" }),
    textoClip("t3", { literal: "🔥" }, { ...V2, fuente: "Inter-Bold" }),
  ]);
  assert.deepEqual([...fuentesDelDocumento(doc, T_E)].sort(), ["Anton-Regular", "CreatvEmoji", "Inter-Bold"]);
  assert.deepEqual([...fuentesDelDocumento(doc, T0)].sort(), ["Anton-Regular", "Inter-Bold"], "sin la fuente de emojis no hay nada que bajar");
  assert.deepEqual([...fuentesDelDocumento(doc, null)].sort(), ["Anton-Regular", "Inter-Bold"], "sin tabla, solo las fuentes");
  assert.ok(fuentesDelDocumento(doc, T_E) instanceof Set);
});

test("fuentesDelDocumento: lo que trae cada destino cuenta (el documento va SIN resolver)", async () => {
  const { fuentesDelDocumento } = await import("../../static/editor/vista.js");
  const doc = docDeTextos([textoClip("t1", { variable: "hook" }, { ...V2, fuente: "Pacifico-Regular" })], {
    variables: { textos: { hook: { es_CO: "Llévalo hoy", en_US: "Get it now 🔥" } }, precios: {} },
  });
  assert.deepEqual([...fuentesDelDocumento(doc, T_E)].sort(), ["CreatvEmoji", "Pacifico-Regular"]);
  doc.variables.textos.hook.en_US = "Get it now";
  assert.deepEqual([...fuentesDelDocumento(doc, T_E)], ["Pacifico-Regular"]);
});

test("fuentesDelDocumento: un texto v1 con emoji no baja la fuente de emojis (v1 no lo dibuja); un emoji sin cobertura tampoco", async () => {
  const { fuentesDelDocumento } = await import("../../static/editor/vista.js");
  const v1 = docDeTextos([textoClip("t1", { literal: "🔥 hola" }, { fuente: "Inter-Bold" })]);
  assert.deepEqual([...fuentesDelDocumento(v1, T_E)], ["Inter-Bold"]);
  const sinCobertura = docDeTextos([textoClip("t1", { literal: "🍕 hola" }, { ...V2, fuente: "Inter-Bold" })]);
  assert.deepEqual([...fuentesDelDocumento(sinCobertura, T_E)], ["Inter-Bold"], "el 🍕 la tabla de prueba no lo trae");
  const tono = docDeTextos([textoClip("t1", { literal: "👍🏽" }, { ...V2, fuente: "Inter-Bold" })]);
  assert.deepEqual([...fuentesDelDocumento(tono, T_E)].sort(), ["CreatvEmoji", "Inter-Bold"], "el tono de piel se quita y queda el 👍");
});

test("fuentesDelDocumento: no lanza con una fuente que la tabla no trae, un documento vacío o clips raros", async () => {
  const { fuentesDelDocumento } = await import("../../static/editor/vista.js");
  const raro = docDeTextos([
    textoClip("t1", { literal: "🔥" }, { ...V2, fuente: "Inexistente" }),
    { id: "t2", inicio_ms: 0, duracion_ms: 10 },
    textoClip("t3", { variable: "precio" }, { ...V2, fuente: "Inter-Bold" }),
  ]);
  assert.deepEqual([...fuentesDelDocumento(raro, T_E)].sort(), ["Inexistente", "Inter-Bold"]);
  assert.equal(fuentesDelDocumento(null, T_E).size, 0);
  assert.equal(fuentesDelDocumento({}, T_E).size, 0);
  assert.equal(fuentesDelDocumento({ pistas: [{ tipo: "audio", clips: [{ id: "a" }] }] }, T_E).size, 0);
});

test("fuentesDelDocumento: con subtítulos, las dos Inter que dibuja el lienzo; sin palabras ni fuentes, ninguna", async () => {
  const { fuentesDelDocumento } = await import("../../static/editor/vista.js");
  const sin = docDeTextos([], { subtitulos: { estilo_id: "karaoke", posicion: 0.78, palabras: {} } });
  assert.equal(fuentesDelDocumento(sin, T0).size, 0);
  const conPalabras = docDeTextos([], { subtitulos: { estilo_id: "karaoke", palabras: { es_CO: [{ t_ms: 0, dur_ms: 100, texto: "Hola" }] } } });
  assert.deepEqual([...fuentesDelDocumento(conPalabras, T0)].sort(), ["Inter-Bold", "Inter-SemiBold"]);
  const conFuentes = docDeTextos([], { subtitulos: { estilo_id: "karaoke", palabras: {}, fuentes: { es_CO: [{ tipo: "voz" }] } } });
  assert.deepEqual([...fuentesDelDocumento(conFuentes, T0)].sort(), ["Inter-Bold", "Inter-SemiBold"]);
  const apagados = docDeTextos([], { subtitulos: { visibles: false, palabras: { es_CO: [{ t_ms: 0, dur_ms: 100, texto: "Hola" }] } } });
  assert.equal(fuentesDelDocumento(apagados, T0).size, 0);
});

// `document.fonts.load` de mentira: anota lo que se le pide y deja resolver cada pedido a mano.
function fuentesFalsas({ cfg, rechazar = [] } = {}) {
  const pedidos = [];
  const pendientes = [];
  const cuadros = [];
  globalThis.document = {
    fonts: {
      load: (f) => {
        pedidos.push(f);
        if (rechazar.some((r) => f.includes(r))) return Promise.reject(new Error("no bajó"));
        return new Promise((resolver) => pendientes.push(resolver));
      },
    },
  };
  const falsa = {
    cfg: cfg ?? { fuentes: ["Inter-Bold", "Anton-Regular", "Pacifico-Regular"], emoji: { familia: "CreatvEmoji" } },
    fuentesPedidas: new Map(), generacionFuentes: 0, pedirCuadro: () => cuadros.push(falsa.generacionFuentes),
  };
  return { falsa, pedidos, cuadros, resolverTodo: () => pendientes.splice(0).forEach((r) => r([])) };
}

test("cargarFuentes baja solo lo que falta, sube la generación y pide un cuadro cuando cada una llega", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const { falsa, pedidos, cuadros, resolverTodo } = fuentesFalsas();
  try {
    const espera = VistaPrevia.prototype.cargarFuentes.call(falsa, ["Anton-Regular", "CreatvEmoji", "Desconocida", "Anton-Regular"]);
    assert.deepEqual(pedidos, ['32px "Anton-Regular"', '32px "CreatvEmoji"'], "una vez cada una, solo las que la página declara");
    assert.equal(falsa.generacionFuentes, 0, "todavía bajando");
    resolverTodo();
    await espera;
    assert.equal(falsa.generacionFuentes, 2);
    assert.deepEqual(cuadros, [1, 2]);
    // otra vez las mismas: nada que bajar ni que redibujar
    await VistaPrevia.prototype.cargarFuentes.call(falsa, ["Anton-Regular", "CreatvEmoji"]);
    assert.equal(pedidos.length, 2);
    assert.equal(falsa.generacionFuentes, 2);
    // una nueva
    const otra = VistaPrevia.prototype.cargarFuentes.call(falsa, ["Pacifico-Regular", "Anton-Regular"]);
    resolverTodo();
    await otra;
    assert.deepEqual(pedidos.slice(2), ['32px "Pacifico-Regular"']);
    assert.equal(falsa.generacionFuentes, 3);
  } finally {
    delete globalThis.document;
  }
});

test("cargarFuentes: quien pide una que ya está bajando espera a la misma, sin pedirla otra vez", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const { falsa, pedidos, resolverTodo } = fuentesFalsas();
  try {
    const a = VistaPrevia.prototype.cargarFuentes.call(falsa, ["Anton-Regular"]);
    let listoB = false;
    const b = VistaPrevia.prototype.cargarFuentes.call(falsa, ["Anton-Regular", "Inter-Bold"]).then(() => { listoB = true; });
    assert.deepEqual(pedidos, ['32px "Anton-Regular"', '32px "Inter-Bold"']);
    await Promise.resolve();
    assert.equal(listoB, false, "espera a las dos");
    resolverTodo();
    await Promise.all([a, b]);
    assert.equal(listoB, true);
    assert.equal(falsa.generacionFuentes, 2);
  } finally {
    delete globalThis.document;
  }
});

test("cargarFuentes: una fuente que no baja no rompe nada, no sube la generación y no se pide una y otra vez", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const { falsa, pedidos, resolverTodo } = fuentesFalsas({ rechazar: ["Pacifico"] });
  try {
    const espera = VistaPrevia.prototype.cargarFuentes.call(falsa, ["Pacifico-Regular", "Anton-Regular"]);
    resolverTodo();
    await espera;                                   // no lanza
    assert.equal(falsa.generacionFuentes, 1, "solo la que sí bajó");
    await VistaPrevia.prototype.cargarFuentes.call(falsa, ["Pacifico-Regular"]);
    assert.equal(pedidos.length, 2);
    // sin document.fonts (un navegador raro) tampoco lanza
    delete globalThis.document;
    globalThis.document = {};
    await VistaPrevia.prototype.cargarFuentes.call(falsa, ["Inter-Bold"]);
    assert.equal(falsa.generacionFuentes, 1);
    await VistaPrevia.prototype.cargarFuentes.call(falsa, []);                  // sin nada que pedir tampoco
  } finally {
    delete globalThis.document;
  }
});

test("setDocumento pide las fuentes que el documento nuevo usa (las que ya bajaron no se repiten) y sigue re-resolviendo el destino", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const pedidos = [];
  const elegidos = [];
  const falsa = {
    cfg: { tipografia: T_E }, destinoActual: null, documentoOriginal: null,
    cargarFuentes: (ids) => { pedidos.push([...ids].sort()); return Promise.resolve(); },
    elegirDestino: (d) => elegidos.push(d),
  };
  const doc = docDeTextos([textoClip("t1", { literal: "OFERTA 🔥" }, { ...V2, fuente: "Anton-Regular" })]);
  VistaPrevia.prototype.setDocumento.call(falsa, doc);
  assert.equal(falsa.documentoOriginal, doc);
  assert.deepEqual(pedidos, [["Anton-Regular", "CreatvEmoji"]]);
  assert.deepEqual(elegidos, [], "antes de iniciar() todavía no hay destino");
  falsa.destinoActual = "es_CO";
  VistaPrevia.prototype.setDocumento.call(falsa, doc);
  assert.deepEqual(elegidos, ["es_CO"]);
});

test("iniciar baja solo las fuentes del documento (no todas las de la página) y espera a que lleguen", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const pedidos = [];
  const elemento = () => ({ append() {}, addEventListener() {}, setAttribute() {}, textContent: "", value: "", hidden: false });
  const antes = [globalThis.document, globalThis.Option, globalThis.requestAnimationFrame];
  globalThis.document = { getElementById: elemento, addEventListener() {}, querySelector: elemento };
  globalThis.Option = class { constructor(texto, valor) { this.texto = texto; this.valor = valor; } };
  globalThis.requestAnimationFrame = () => 0;
  let llego = false;
  const falsa = {
    datos: { destinos: ["es_CO", "en_US"] },
    cfg: { tipografia: T_E, fps: 30, fuentes: ["Inter-Bold", "Anton-Regular", "Pacifico-Regular"], emoji: { familia: "CreatvEmoji" } },
    documentoOriginal: docDeTextos([textoClip("t1", { literal: "OFERTA" }, { fuente: "Anton-Regular" })]),
    cargarFuentes: (ids) => {
      pedidos.push([...ids]);
      return new Promise((resolver) => setTimeout(() => { llego = true; resolver(); }, 5));
    },
    elegirDestino: () => { assert.equal(llego, true, "el primer destino se elige con las fuentes ya bajadas"); },
    vigilarPendientes: () => {},
    ocupado: () => false,
    cuadro: () => {},
  };
  try {
    await VistaPrevia.prototype.iniciar.call(falsa);
    assert.deepEqual(pedidos, [["Anton-Regular"]]);
  } finally {
    [globalThis.document, globalThis.Option, globalThis.requestAnimationFrame] = antes;
    if (antes[0] === undefined) delete globalThis.document;
    if (antes[1] === undefined) delete globalThis.Option;
    if (antes[2] === undefined) delete globalThis.requestAnimationFrame;
  }
});

test("crearRecursos trae la tabla tipográfica y la generación de fuentes (lo que lienzo.js le pasa a rasterizarTexto)", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const falsa = { ctx: {}, cfg: { tipografia: T_E }, generacionFuentes: 4, materialesVigentes: {} };
  const recursos = VistaPrevia.prototype.crearRecursos.call(falsa);
  assert.equal(recursos.tabla, T_E);
  assert.equal(recursos.generacionFuentes, 4);
  falsa.generacionFuentes = 5;
  assert.equal(recursos.generacionFuentes, 5, "se lee en cada cuadro");
});

// El lienzo falso de imagenTenida: anota lo que se le hace, en orden.
function lienzoTenido() {
  const hechos = [];
  const lienzos = [];
  const antes = globalThis.document;
  globalThis.document = {
    createElement: () => {
      const orden = [];
      const ctx = {
        set fillStyle(v) { orden.push(["fillStyle", v]); },
        set globalCompositeOperation(v) { orden.push(["globalCompositeOperation", v]); },
        fillRect(...a) { orden.push(["fillRect", ...a]); },
        drawImage(...a) { orden.push(["drawImage", ...a]); },
      };
      const lienzo = { width: 0, height: 0, getContext: () => ctx, orden };
      lienzos.push(lienzo);
      return lienzo;
    },
  };
  return { hechos, lienzos, restaurar: () => { if (antes === undefined) delete globalThis.document; else globalThis.document = antes; } };
}

test("imagenTenida: el color relleno y la imagen encima con destination-in (color constante × el mismo alfa); caché por material y color", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const { lienzos, restaurar } = lienzoTenido();
  const img = { complete: true, naturalWidth: 512, naturalHeight: 256 };
  const falsa = {
    ctx: {}, cfg: { tipografia: T0 }, generacionFuentes: 0,
    materialesVigentes: { 9: { id: 9, tipo: "imagen", url: "https://r2/s.png" } },
    imagenes: new Map([[9, img]]), imagenesFallidas: new Set(), imagenesTenidas: new Map(),
  };
  try {
    const recursos = VistaPrevia.prototype.crearRecursos.call(falsa);
    const a = recursos.imagenTenida(9, "#FFD400");
    assert.deepEqual([a.width, a.height], [512, 256], "el tamaño natural de la imagen");
    assert.deepEqual(a.orden, [
      ["fillStyle", "#FFD400"], ["fillRect", 0, 0, 512, 256], ["globalCompositeOperation", "destination-in"], ["drawImage", img, 0, 0],
    ]);
    assert.equal(recursos.imagenTenida(9, "#FFD400"), a, "la misma, sin redibujarla");
    assert.equal(lienzos.length, 1);
    const b = recursos.imagenTenida(9, "#E11D48");
    assert.notEqual(b, a);
    assert.deepEqual([...falsa.imagenesTenidas.keys()], ["9:#FFD400", "9:#E11D48"]);
    // la imagen todavía no cargó: nada que teñir, y no se guarda un lienzo vacío
    falsa.imagenes.set(9, { complete: false, naturalWidth: 0, naturalHeight: 0 });
    assert.equal(recursos.imagenTenida(9, "#00FF00"), null);
    assert.equal(falsa.imagenesTenidas.has("9:#00FF00"), false);
    // un material que ya no está
    assert.equal(recursos.imagenTenida(77, "#FFD400"), null);
  } finally {
    restaurar();
  }
});

test("imagenTenida: la caché tiene tope (cada color de la paleta guarda un lienzo del tamaño de la imagen)", async () => {
  const { VistaPrevia, TOPE_TENIDAS } = await import("../../static/editor/vista.js");
  const { restaurar } = lienzoTenido();
  const img = { complete: true, naturalWidth: 8, naturalHeight: 8 };
  const falsa = {
    ctx: {}, cfg: { tipografia: T0 }, generacionFuentes: 0, materialesVigentes: { 9: { id: 9, tipo: "imagen" } },
    imagenes: new Map([[9, img]]), imagenesFallidas: new Set(), imagenesTenidas: new Map(),
  };
  try {
    const recursos = VistaPrevia.prototype.crearRecursos.call(falsa);
    const primero = recursos.imagenTenida(9, "#000000");
    for (let n = 1; n <= TOPE_TENIDAS + 5; n++) recursos.imagenTenida(9, `#${String(n).padStart(6, "0")}`);
    assert.equal(falsa.imagenesTenidas.size, TOPE_TENIDAS);
    assert.equal(falsa.imagenesTenidas.has("9:#000000"), false, "sale el más viejo");
    assert.notEqual(recursos.imagenTenida(9, "#000000"), primero);
  } finally {
    restaurar();
  }
});

test("imagenTenida: un acierto pasa al final de la caché y sobrevive a la expulsión del más viejo (LRU)", async () => {
  const { VistaPrevia, TOPE_TENIDAS } = await import("../../static/editor/vista.js");
  const { restaurar } = lienzoTenido();
  const img = { complete: true, naturalWidth: 8, naturalHeight: 8 };
  const falsa = {
    ctx: {}, cfg: { tipografia: T0 }, generacionFuentes: 0, materialesVigentes: { 9: { id: 9, tipo: "imagen" } },
    imagenes: new Map([[9, img]]), imagenesFallidas: new Set(), imagenesTenidas: new Map(),
  };
  const color = (n) => `#${String(n).padStart(6, "0")}`;
  try {
    const recursos = VistaPrevia.prototype.crearRecursos.call(falsa);
    const viejo = recursos.imagenTenida(9, color(0));
    for (let n = 1; n < TOPE_TENIDAS; n++) recursos.imagenTenida(9, color(n));
    assert.equal(falsa.imagenesTenidas.size, TOPE_TENIDAS);
    assert.equal(recursos.imagenTenida(9, color(0)), viejo, "un acierto devuelve el mismo lienzo");
    assert.equal([...falsa.imagenesTenidas.keys()].at(-1), `9:${color(0)}`, "y lo pasa al final");
    recursos.imagenTenida(9, "#FFFFFF");                          // una nueva: sale el más viejo, que ahora es color(1)
    assert.equal(falsa.imagenesTenidas.size, TOPE_TENIDAS);
    assert.equal(falsa.imagenesTenidas.has(`9:${color(0)}`), true, "el que tuvo un acierto sobrevive");
    assert.equal(falsa.imagenesTenidas.has(`9:${color(1)}`), false, "salió el siguiente más viejo");
    assert.equal(recursos.imagenTenida(9, color(0)), viejo);
  } finally {
    restaurar();
  }
});

test("renovarPendientes suelta los lienzos teñidos del material cuyo archivo cambió (y solo los suyos)", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const falsa = {
    porRenovar: new Set([9]), materialesVigentes: {}, videos: { renovar() {} }, audio: { buffers: new Map(), fallidos: new Set() },
    imagenes: new Map([[9, {}], [10, {}]]), imagenesFallidas: new Set(), imagenesLigeras: new Map(), imagenesLigerasFallidas: new Set(),
    imagenesTenidas: new Map([["9:#FFD400", {}], ["9:#E11D48", {}], ["10:#FFD400", {}], ["99:#FFD400", {}]]),
    fallasCarga: new Set(), mostrarFallas() {},
  };
  VistaPrevia.prototype.renovarPendientes.call(falsa);
  assert.deepEqual([...falsa.imagenesTenidas.keys()], ["10:#FFD400", "99:#FFD400"], "«9:» no es «99:» ni «10:»");
  assert.equal(falsa.imagenes.has(9), false);
});

test("medidasTexto pide el mismo dibujo que lienzo.js: con la tabla, la escala del clip y la generación de fuentes", async () => {
  const { VistaPrevia } = await import("../../static/editor/vista.js");
  const doc = docDeTextos([
    { ...textoClip("t1", { literal: "Hola" }, { ...V2, fuente: "Inter-Bold" }), transform: { escala: 1.5 },
      keyframes: [{ t_ms: 500, transform: { escala: 3 } }] },
  ]);
  const opciones = [];
  const rasterizar = (literal, estilo, formato, o) => { opciones.push(o); return { ancho: 221, alto: 125 }; };
  const falsa = { doc, tiempo: () => 100, recursos: { tabla: T0, generacionFuentes: 6 } };
  assert.deepEqual(VistaPrevia.prototype.medidasTexto.call(falsa, 100, rasterizar), { t1: [221, 125] });
  assert.deepEqual(opciones, [{ tabla: T0, escala: 3, generacion: 6 }]);
});
