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
  for (const m of ["dibujar", "moverCabezal"]) {
    assert.equal(typeof lt.LineaTiempo.prototype[m], "function", `LineaTiempo.${m}`);
  }
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

test("infoDe arma el mapa {id: {duracion_ms, tiene_audio}} que piden las operaciones", async () => {
  const { infoDe } = await import("../../static/editor/vista.js");
  const info = infoDe({
    1: { id: 1, tipo: "video", duracion_ms: 4000, tiene_audio: false },
    2: { id: 2, tipo: "audio", duracion_ms: 2000, tiene_audio: null },
    3: { id: 3, tipo: "imagen", duracion_ms: null },
    4: { id: 4, tipo: "video", duracion_ms: 0 },                   // sin medir: desconocida, nunca 0
    5: null,
  });
  assert.deepEqual(info, {
    1: { duracion_ms: 4000, tiene_audio: false },
    2: { duracion_ms: 2000, tiene_audio: null },
    3: { duracion_ms: null, tiene_audio: null },
    4: { duracion_ms: null, tiene_audio: null },
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
  assert.equal(falsa.audio.buffers.has(1), true);
  assert.deepEqual(llamadas, [["cuadro"], ["pagina", ["1", "3", "5"]]]);
  llamadas.length = 0;
  falsa.reproduciendo = false;
  falsa.renovarPendientes();                                                          // lo llama pausar()
  assert.deepEqual(llamadas, [["renovar", ["1", "3", "5"], [1, 3, 5]], ["fallas"]]);
  assert.equal(falsa.imagenes.has(3), false);
  assert.equal(falsa.audio.buffers.has(1), false);
  llamadas.length = 0;
  falsa.renovarPendientes();                                                          // una sola vez
  assert.deepEqual(llamadas, []);
});
