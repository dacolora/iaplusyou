// Los módulos de navegador no se pueden ejecutar en Node (usan el DOM al
// llamarlos), pero sí importarse: esto atrapa errores de sintaxis y de
// importación antes de abrir la página. Importarlos también prueba que no
// tocan `document` ni `window` al cargar (en Node no existen: la importación
// fallaría). vista.js y linea_tiempo.js ya no arrancan solos desde la capa 4a
// (lo hace pagina_editor.js, que sí lee la página al cargar y no se importa).
import { test } from "node:test";
import assert from "node:assert/strict";

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
  assert.equal(falsa.audio.buffers.has(1), true);
  assert.deepEqual(llamadas, [["cuadro"], ["pagina", ["1", "3", "5"]]]);
  llamadas.length = 0;
  falsa.reproduciendo = false;
  falsa.renovarPendientes();                                                          // lo llama pausar()
  assert.deepEqual(llamadas, [["renovar", ["1", "3", "5"], [1, 3, 5]], ["fallas"]]);
  assert.equal(falsa.imagenes.has(3), false);
  assert.equal(falsa.imagenesLigeras.has(3), false);
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
