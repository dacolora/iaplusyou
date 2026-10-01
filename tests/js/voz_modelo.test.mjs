// La voz en off de la pestaña «Audio» (capa 5a, Task 8): lo puro de
// voz_modelo.js — con qué formato graba cada navegador, el reloj, por qué no
// se puede grabar, el estado del texto, el filtro de voces, el idioma inicial,
// el botón «Crear la voz», lo que se guarda para retomar tras recargar y lo
// que se dice al agregar la voz.
import { test } from "node:test";
import assert from "node:assert/strict";
import { ponerTextos } from "../../static/editor/textos.js";
import {
  avisoAgregada, botonCrear, corteGrabacion, elegirGrabacion, idiomaDeVoz, encargoVozGuardado, ENCARGO_VOZ_MAX_MS, estadoTexto, extensionDeMime, filtrarVoces,
  FILTROS_VOZ,
  firmaPedido, FORMATOS_GRABACION, horaLocal, idiomaInicial, MAX_GRABACION_MS, mensajeGrabacionSubida, mensajeMicrofono,
  motivoSinGrabar, nivelDe, nombreArchivo, relojTexto, textoReloj,
} from "../../static/editor/voz_modelo.js";

const soporta = (lista) => (mime) => lista.includes(mime);

test("elegirGrabacion: el primer formato que el navegador graba, con su extensión", () => {
  assert.deepEqual(FORMATOS_GRABACION, [["audio/webm;codecs=opus", ".webm"], ["audio/mp4", ".m4a"],
    ["audio/ogg;codecs=opus", ".ogg"], ["audio/webm", ".webm"]]);
  // Chrome, Edge, Firefox
  assert.deepEqual(elegirGrabacion(soporta(["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"])),
    { mime: "audio/webm;codecs=opus", ext: ".webm" });
  // Safari: solo mp4 (AAC), que el servidor recibe como .m4a
  assert.deepEqual(elegirGrabacion(soporta(["audio/mp4"])), { mime: "audio/mp4", ext: ".m4a" });
  assert.deepEqual(elegirGrabacion(soporta(["audio/webm"])), { mime: "audio/webm", ext: ".webm" });
  // ninguno, o un navegador sin isTypeSupported
  assert.equal(elegirGrabacion(soporta([])), null);
  assert.equal(elegirGrabacion(null), null);
  // un isTypeSupported que lanza no rompe la página
  assert.equal(elegirGrabacion(() => { throw new Error("x"); }), null);
});

test("relojTexto y textoReloj: minutos y segundos cortados, como un reloj", () => {
  assert.equal(MAX_GRABACION_MS, 300000);
  assert.equal(relojTexto(7000), "0:07");
  assert.equal(relojTexto(7999), "0:07");
  assert.equal(relojTexto(299999), "4:59");
  assert.equal(relojTexto(300000), "5:00");
  assert.equal(relojTexto(0), "0:00");
  assert.equal(relojTexto(-5), "0:00");
  assert.equal(relojTexto(undefined), "0:00");
  assert.equal(relojTexto(65000), "1:05");
  assert.equal(textoReloj(7000, MAX_GRABACION_MS), "0:07 de 5:00");
});

test("motivoSinGrabar: página no segura, navegador sin grabación o nada que decir", () => {
  // sin navigator.mediaDevices (http fuera de localhost)
  assert.equal(motivoSinGrabar({ hayMediaDevices: false, hayMediaRecorder: true, formato: { mime: "audio/webm", ext: ".webm" } }),
    "grab.inseguro");
  // sin MediaRecorder o sin ningún formato que sepa grabar
  assert.equal(motivoSinGrabar({ hayMediaDevices: true, hayMediaRecorder: false, formato: null }), "grab.no_soporta");
  assert.equal(motivoSinGrabar({ hayMediaDevices: true, hayMediaRecorder: true, formato: null }), "grab.no_soporta");
  // todo bien
  assert.equal(motivoSinGrabar({ hayMediaDevices: true, hayMediaRecorder: true, formato: { mime: "audio/mp4", ext: ".m4a" } }), null);
  // si se sabe que la página ES segura, faltar mediaDevices es un navegador viejo, no la dirección
  assert.equal(motivoSinGrabar({ hayMediaDevices: false, hayMediaRecorder: false, formato: null, seguro: true }), "grab.no_soporta");
  assert.equal(motivoSinGrabar({ hayMediaDevices: true, hayMediaRecorder: true, formato: { mime: "a", ext: ".webm" }, seguro: false }),
    "grab.inseguro");
});

test("mensajeMicrofono: el porqué en llano según el error del navegador", () => {
  assert.equal(mensajeMicrofono("NotAllowedError"), "grab.permiso");
  assert.equal(mensajeMicrofono("SecurityError"), "grab.permiso");
  assert.equal(mensajeMicrofono("NotFoundError"), "grab.sin_micro");
  assert.equal(mensajeMicrofono("OverconstrainedError"), "grab.sin_micro");
  assert.equal(mensajeMicrofono("NotReadableError"), "grab.error");
  assert.equal(mensajeMicrofono(undefined), "grab.error");
});

test("estadoTexto: vacío, justo en el tope y pasado", () => {
  assert.deepEqual(estadoTexto("", 10), { n: 0, valido: false, clave: "voz.texto_vacio" });
  assert.deepEqual(estadoTexto("   \n ", 10), { n: 5, valido: false, clave: "voz.texto_vacio" });
  assert.deepEqual(estadoTexto(null, 10), { n: 0, valido: false, clave: "voz.texto_vacio" });
  assert.deepEqual(estadoTexto("0123456789", 10), { n: 10, valido: true, clave: null });
  assert.deepEqual(estadoTexto("Hola", 10), { n: 4, valido: true, clave: null });
  assert.deepEqual(estadoTexto("01234567890", 10), { n: 11, valido: false, clave: "voz.texto_largo" });
});

const FICHAS = [
  { nombre: "Rachel", genero: "mujer", genero_nombre: "Mujer", tono: "calmada" },
  { nombre: "Adam", genero: "hombre", genero_nombre: "Hombre", tono: "grave" },
  { nombre: "River", genero: "neutra", genero_nombre: "Neutra", tono: "segura" },
  { nombre: "Sarah", genero: "mujer", genero_nombre: "Mujer", tono: "suave" },
];

test("filtrarVoces: Todas, Mujer u Hombre, en el orden de la galería", () => {
  assert.deepEqual(FILTROS_VOZ.map((f) => f.valor), ["", "mujer", "hombre"]);
  assert.deepEqual(FILTROS_VOZ.map((f) => f.clave), ["voz.filtro_todas", "voz.filtro_mujer", "voz.filtro_hombre"]);
  assert.deepEqual(filtrarVoces(FICHAS, "").map((f) => f.nombre), ["Rachel", "Adam", "River", "Sarah"]);
  assert.deepEqual(filtrarVoces(FICHAS, null).map((f) => f.nombre), ["Rachel", "Adam", "River", "Sarah"]);
  assert.deepEqual(filtrarVoces(FICHAS, "mujer").map((f) => f.nombre), ["Rachel", "Sarah"]);
  assert.deepEqual(filtrarVoces(FICHAS, "hombre").map((f) => f.nombre), ["Adam"]);
  assert.deepEqual(filtrarVoces(null, "mujer"), []);
});

test("idiomaInicial: el idioma del destino que se ve si la voz lo habla; si no, el del proyecto", () => {
  assert.equal(idiomaInicial("en_US", ["es", "en", "pt"], "es"), "en");
  assert.equal(idiomaInicial("fr_FR", ["es", "en", "pt"], "es"), "es");
  assert.equal(idiomaInicial("es", ["es", "en", "pt"], "pt"), "es");
  assert.equal(idiomaInicial(null, ["es", "en", "pt"], "pt"), "pt");
  // un defecto que no está en la lista cae al primero
  assert.equal(idiomaInicial("fr_FR", ["es", "en"], "fr"), "es");
  assert.equal(idiomaInicial("fr_FR", [], "fr"), null);
});

test("botonCrear: el precio tal cual lo escribió el servidor, gratis si ya existe, y cuándo se apaga", () => {
  assert.deepEqual(botonCrear({ vacio: true }), { texto: "Escribe lo que va a decir la voz.", desactivado: true });
  assert.deepEqual(botonCrear({ calculando: true }), { texto: "Calculando el precio…", desactivado: true });
  // sin precio no se paga: el clic solo vuelve a pedirlo (activo)
  assert.deepEqual(botonCrear({ error: true }), { texto: "No se pudo calcular el precio: vuelve a intentar.", desactivado: false });
  assert.deepEqual(botonCrear({ precio: "US$ 0,03 aprox." }), { texto: "Crear la voz (US$ 0,03 aprox.)", desactivado: false });
  assert.deepEqual(botonCrear({ gratis: true, precio: "US$ 0,03 aprox." }),
    { texto: "Agregar la voz (ya la tienes, gratis)", desactivado: false });
  assert.deepEqual(botonCrear({ corriendo: true, etapa: "Preparando sus subtítulos" }),
    { texto: "Creando la voz… Preparando sus subtítulos", desactivado: true });
  // la primera etapa se llama igual que el botón: no se repite
  assert.deepEqual(botonCrear({ corriendo: true, etapa: "Creando la voz" }), { texto: "Creando la voz…", desactivado: true });
  assert.deepEqual(botonCrear({ corriendo: true }), { texto: "Creando la voz…", desactivado: true });
  // nada pedido todavía (sin precio ni cálculo): apagado
  assert.equal(botonCrear({}).desactivado, true);
  // con la edición cambiada en otra pestaña no se paga nada
  assert.equal(botonCrear({ precio: "US$ 0,03 aprox.", conflicto: true }).desactivado, true);
});

test("botonCrear en inglés: las claves de textos.js", () => {
  ponerTextos({ "voz.crear_precio": "Create the voice ({precio})" }, "en");
  try {
    assert.equal(botonCrear({ precio: "US$0.03 approx." }).texto, "Create the voice (US$0.03 approx.)");
  } finally {
    ponerTextos({}, "es");
  }
});

test("firmaPedido: lo que cambia el precio (el texto como lo cuenta el servidor, voz, velocidad, idioma)", () => {
  const a = firmaPedido({ texto: "  Hola   mundo\n", voz: "Rachel", velocidad: "normal", idioma: "es" });
  assert.equal(a, firmaPedido({ texto: "Hola mundo", voz: "Rachel", velocidad: "normal", idioma: "es" }));
  assert.notEqual(a, firmaPedido({ texto: "Hola mundo", voz: "Adam", velocidad: "normal", idioma: "es" }));
  assert.notEqual(a, firmaPedido({ texto: "Hola mundo", voz: "Rachel", velocidad: "rapida", idioma: "es" }));
  assert.notEqual(a, firmaPedido({ texto: "Hola mundo", voz: "Rachel", velocidad: "normal", idioma: "en" }));
});

test("encargoVozGuardado: solo el de ESE trabajo, con su forma y de hace menos de media hora", () => {
  const clave = "a".repeat(64);
  const ahora = 1_000_000_000;
  const bueno = { job: "acme__ed7__voz", sello: ahora - 1000, clave, idioma: "es" };
  assert.deepEqual(encargoVozGuardado(bueno, "acme__ed7__voz", ahora), { clave, idioma: "es", habla: null });
  assert.deepEqual(encargoVozGuardado({ ...bueno, idioma: null, habla: "en" }, "acme__ed7__voz", ahora),
    { clave, idioma: null, habla: "en" });
  assert.equal(encargoVozGuardado({ ...bueno, habla: "ingles" }, "acme__ed7__voz", ahora), null);
  assert.equal(encargoVozGuardado(bueno, "otro", ahora), null);
  assert.equal(encargoVozGuardado({ ...bueno, sello: ahora - ENCARGO_VOZ_MAX_MS - 1 }, "acme__ed7__voz", ahora), null);
  assert.equal(encargoVozGuardado({ ...bueno, sello: ahora + 5 * 60 * 1000 }, "acme__ed7__voz", ahora), null);
  assert.equal(encargoVozGuardado({ ...bueno, clave: "xyz" }, "acme__ed7__voz", ahora), null);
  assert.equal(encargoVozGuardado({ ...bueno, idioma: "esp" }, "acme__ed7__voz", ahora), null);
  assert.equal(encargoVozGuardado(null, "acme__ed7__voz", ahora), null);
  assert.equal(encargoVozGuardado("x", "acme__ed7__voz", ahora), null);
});

test("nivelDe: el nivel del micrófono (0 en silencio, 1 a tope) desde los bytes del AnalyserNode", () => {
  assert.equal(nivelDe(new Uint8Array([128, 128, 128, 128])), 0);
  assert.equal(nivelDe(new Uint8Array([255, 0, 255, 0])), 1);
  const medio = nivelDe(new Uint8Array([160, 96, 160, 96]));
  assert.ok(medio > 0.3 && medio < 1, medio);
  assert.equal(nivelDe(new Uint8Array([])), 0);
  assert.equal(nivelDe(null), 0);
});

test("horaLocal y nombreArchivo: lo que viaja con la grabación", () => {
  assert.equal(horaLocal(new Date(2026, 9, 1, 9, 5)), "09:05");
  assert.equal(horaLocal(new Date(2026, 9, 1, 23, 59)), "23:59");
  assert.equal(nombreArchivo(".m4a"), "grabacion.m4a");
  assert.equal(nombreArchivo(".webm"), "grabacion.webm");
  assert.equal(nombreArchivo("raro"), "grabacion.webm");
});

test("mensajeGrabacionSubida: el error de la subida, en llano", () => {
  assert.equal(mensajeGrabacionSubida({ red: true }), "Sin conexión: no se pudo subir. Vuelve a intentar.");
  assert.equal(mensajeGrabacionSubida({ redirigido: true, status: 200 }), "Tu sesión venció: vuelve a entrar y súbelo otra vez.");
  assert.equal(mensajeGrabacionSubida({ status: 400, cuerpo: { error: "La grabación dura más de 5 minutos." } }),
    "La grabación dura más de 5 minutos.");
  assert.equal(mensajeGrabacionSubida({ status: 502, cuerpo: null }), "No se pudo subir la grabación (error 502).");
  assert.equal(mensajeGrabacionSubida({ status: 400, cuerpo: { error: "" } }), "No se pudo subir la grabación (error 400).");
});

test("avisoAgregada: qué se dice al agregar una voz o una grabación", () => {
  assert.deepEqual(avisoAgregada({ tipo: "ia", conPalabras: true, cortadaMs: null }),
    { texto: "Voz agregada en el cabezal. Sus subtítulos ya están listos: ponlos gratis en «Subtítulos».", irSubtitulos: true, error: false });
  // Whisper falló: la voz (pagada) entra igual y se dice que los subtítulos se generan aparte
  assert.deepEqual(avisoAgregada({ tipo: "ia", conPalabras: false, cortadaMs: null }),
    { texto: "Voz agregada en el cabezal. Sus subtítulos no se pudieron preparar: genéralos en «Subtítulos».", irSubtitulos: true,
      error: false });
  // no cupo entera: se dice hasta dónde quedó (con los subtítulos a mano si los tiene)
  assert.deepEqual(avisoAgregada({ tipo: "ia", conPalabras: true, cortadaMs: 12400 }),
    { texto: "La voz dura más que lo que queda del video: quedó de 0:12.", irSubtitulos: true, error: true });
  assert.deepEqual(avisoAgregada({ tipo: "grabacion", conPalabras: false, cortadaMs: null }),
    { texto: "Grabación agregada en el cabezal.", irSubtitulos: false, error: false });
  assert.deepEqual(avisoAgregada({ tipo: "grabacion", conPalabras: false, cortadaMs: 3000 }),
    { texto: "La voz dura más que lo que queda del video: quedó de 0:03.", irSubtitulos: false, error: true });
});

test("extensionDeMime: la extensión de lo que de verdad grabó el navegador", () => {
  assert.equal(extensionDeMime("audio/webm;codecs=opus"), ".webm");
  assert.equal(extensionDeMime("audio/webm"), ".webm");
  assert.equal(extensionDeMime("audio/mp4"), ".m4a");
  assert.equal(extensionDeMime("audio/mp4;codecs=mp4a.40.2"), ".m4a");
  assert.equal(extensionDeMime("audio/ogg;codecs=opus"), ".ogg");
  assert.equal(extensionDeMime("AUDIO/OGG"), ".ogg");
  // sin decir (un MediaRecorder sin mimeType) o desconocido: webm, lo más común
  assert.equal(extensionDeMime(""), ".webm");
  assert.equal(extensionDeMime(undefined), ".webm");
  assert.equal(extensionDeMime("video/x-matroska"), ".webm");
});

// ---- El panel (voz_panel.js) sin DOM: lo que hace con la edición ----
import * as op from "../../static/editor/operaciones.js";
import { VozPanel } from "../../static/editor/voz_panel.js";
import { docBase } from "./doc_base.mjs";

// Un `editor` como el de pagina_editor.js, con las operaciones de verdad.
function editorFalso({ tiempo = 0, conflicto = false } = {}) {
  const e = { doc: docBase(), seleccion: null, mats: {}, operaciones: [] };
  const info = () => ({
    1: { duracion_ms: 8000, tiene_audio: true }, 2: { duracion_ms: 3000 },
    ...Object.fromEntries(Object.values(e.mats).map((m) => [m.id, { duracion_ms: m.duracion_ms, tiene_audio: null }])),
  });
  return {
    e,
    doc: () => e.doc,
    tiempo: () => tiempo,
    info,
    get seleccion() { return e.seleccion; },
    enConflicto: () => conflicto,
    agregarMateriales: (mapa) => Object.assign(e.mats, mapa),
    operar(nombre, ...args) {
      if (conflicto) return false;
      try {
        const r = op[nombre](e.doc, ...args, info());
        e.doc = r.doc;
        e.seleccion = r.seleccion;
        e.operaciones.push([nombre, ...args]);
        return true;
      } catch {
        return false;
      }
    },
  };
}

function panelFalso(editor) {
  const dichos = [];
  const picos = [];
  return {
    dichos, picos, editor,
    _enConflicto: VozPanel.prototype._enConflicto,
    _decir: (texto, error = false, { irSubtitulos = false } = {}) => dichos.push({ texto, error, irSubtitulos }),
    _esperarPicos: (id) => picos.push(id),
  };
}

const VOZ_IA = { id: 30, tipo: "audio", url: "https://r2/voz.mp3", duracion_ms: 3000, picos: null, origen: "voz",
                 palabras: [{ t_ms: 0, dur_ms: 400, texto: "Hola" }] };

test("VozPanel._agregar: la voz entra en el cabezal como voz, con el idioma del destino, y lo dice", () => {
  const editor = editorFalso({ tiempo: 1000 });
  const panel = panelFalso(editor);
  assert.equal(VozPanel.prototype._agregar.call(panel, VOZ_IA, { tipo: "ia", idioma: "es" }), true);
  const clip = editor.e.doc.pistas.flatMap((p) => p.clips).find((c) => c.id === editor.e.seleccion);
  assert.equal(clip.material_id, 30);
  assert.equal(clip.rol_audio, "voz");
  assert.equal(clip.idioma, "es");
  assert.equal(clip.inicio_ms, 1000);
  assert.equal(clip.por_destino, undefined);                      // se puede recortar (D9)
  assert.equal(editor.e.mats[30], VOZ_IA);                          // la vista previa lo tuvo ANTES de operar
  assert.deepEqual(panel.dichos, [{ texto: "Voz agregada en el cabezal. Sus subtítulos ya están listos: ponlos gratis en «Subtítulos».",
                                    error: false, irSubtitulos: true }]);
  assert.deepEqual(panel.picos, [30]);                             // sin picos todavía: se esperan (gratis)
});

test("VozPanel._agregar: si no cabe entera se dice hasta dónde quedó; sin idioma suena en todos", () => {
  const editor = editorFalso({ tiempo: 6000 });
  const panel = panelFalso(editor);
  const larga = { ...VOZ_IA, id: 31, duracion_ms: 4000, picos: [0.1] };
  assert.equal(VozPanel.prototype._agregar.call(panel, larga, { tipo: "ia", idioma: null }), true);
  const clip = editor.e.doc.pistas.flatMap((p) => p.clips).find((c) => c.id === editor.e.seleccion);
  assert.equal(clip.duracion_ms, 2000);
  assert.equal("idioma" in clip, false);
  assert.deepEqual(panel.dichos, [{ texto: "La voz dura más que lo que queda del video: quedó de 0:02.", error: true, irSubtitulos: true }]);
  assert.deepEqual(panel.picos, []);                               // ya traía sus picos
});

test("VozPanel._agregar: una grabación se anuncia como tal; con la edición cambiada en otra pestaña no se agrega", () => {
  const editor = editorFalso({ tiempo: 0 });
  const panel = panelFalso(editor);
  const grabacion = { id: 40, tipo: "audio", url: "https://r2/g.mp3", duracion_ms: 1500, picos: [0.2], origen: "grabacion" };
  assert.equal(VozPanel.prototype._agregar.call(panel, grabacion, { tipo: "grabacion", idioma: "en" }), true);
  assert.deepEqual(panel.dichos, [{ texto: "Grabación agregada en el cabezal.", error: false, irSubtitulos: false }]);
  const bloqueado = editorFalso({ conflicto: true });
  const p2 = panelFalso(bloqueado);
  assert.equal(VozPanel.prototype._agregar.call(p2, grabacion, { tipo: "grabacion", idioma: "en" }), false);
  assert.equal(bloqueado.e.operaciones.length, 0);
  assert.equal(p2.dichos[0].error, true);
  assert.match(p2.dichos[0].texto, /otra pestaña/);
});

test("VozPanel._retomar: retoma la barra de la voz que se creaba, o pone la que terminó mientras se recargaba", () => {
  const clave = "b".repeat(64);
  const guardado = { job: "acme__ed7__voz", sello: Date.now(), clave, idioma: "es" };
  const llamadas = [];
  const falsa = (vivo) => ({
    datos: { trabajos_vivos: { voz: vivo } },
    _leerEncargo: () => guardado,
    _olvidarEncargo: () => llamadas.push(["olvidar"]),
    seguir: (job, encargo, opciones) => llamadas.push(["seguir", job, encargo, opciones]),
    _traerYAgregar: (encargo, opciones) => llamadas.push(["traer", encargo, opciones]),
  });
  VozPanel.prototype._retomar.call(falsa("acme__ed7__voz"));
  assert.deepEqual(llamadas, [["seguir", "acme__ed7__voz", { clave, idioma: "es", habla: null }, { nuevo: false }]]);
});

test("VozPanel._retomar: el encargo guardado se borra solo DESPUÉS de que la voz entró", async () => {
  const clave = "b".repeat(64);
  const guardado = { job: "acme__ed7__voz", sello: Date.now(), clave, idioma: "es" };
  for (const entro of [true, false]) {
    const llamadas = [];
    let terminar;
    const falsa = {
      datos: { trabajos_vivos: { voz: null } },
      _leerEncargo: () => guardado,
      _olvidarEncargo: () => llamadas.push("olvidar"),
      _traerYAgregar: (encargo, opciones) => {
        llamadas.push(["traer", encargo, opciones]);
        return new Promise((r) => { terminar = r; });
      },
    };
    const espera = VozPanel.prototype._retomar.call(falsa);
    assert.deepEqual(llamadas, [["traer", { clave, idioma: "es", habla: null }, { callado: true }]]);   // todavía no se olvida
    terminar(entro);
    await espera;
    assert.deepEqual(llamadas.slice(1), entro ? ["olvidar"] : []);
  }
});

// ---- Fix round 1 ----

test("corteGrabacion: el navegador corta un segundo antes del tope (el reloj de 250 ms se pasa unos ms)", () => {
  assert.equal(corteGrabacion(MAX_GRABACION_MS), 299000);
  assert.equal(corteGrabacion(60000), 59000);
  assert.equal(corteGrabacion(500), 0);
});

test("idiomaDeVoz: el clip se etiqueta con el destino solo si la voz habla ese idioma", () => {
  assert.deepEqual(idiomaDeVoz("es", "es_CO"), { idioma: "es", habla: null });
  // habla otro idioma: suena en todos (se avisa con `habla`)
  assert.deepEqual(idiomaDeVoz("en", "es_CO"), { idioma: null, habla: "en" });
  // una grabación no dice su idioma: el del destino
  assert.deepEqual(idiomaDeVoz(null, "es_CO"), { idioma: "es", habla: null });
  assert.deepEqual(idiomaDeVoz(undefined, "pt"), { idioma: "pt", habla: null });
  // sin destino que comparar: sin etiqueta ni aviso
  assert.deepEqual(idiomaDeVoz("es", null), { idioma: null, habla: null });
  assert.deepEqual(idiomaDeVoz(null, "raro"), { idioma: null, habla: null });
  // un idioma que no es de dos letras no cuenta
  assert.deepEqual(idiomaDeVoz("espanol", "es_CO"), { idioma: "es", habla: null });
});

test("avisoAgregada: una voz en otro idioma queda sonando en todos y se dice", () => {
  assert.deepEqual(avisoAgregada({ tipo: "ia", conPalabras: true, cortadaMs: null, hablaNombre: "English" }),
    { texto: "La voz habla English: quedó sonando en todos los idiomas. Usa «Suena en» para dejarla solo en uno.",
      irSubtitulos: true, error: false });
  // cortada manda (es lo más importante de saber)
  assert.equal(avisoAgregada({ tipo: "ia", conPalabras: true, cortadaMs: 2000, hablaNombre: "English" }).error, true);
});

test("VozPanel._agregar: una voz que habla otro idioma entra sin idioma y lo dice", () => {
  const editor = editorFalso({ tiempo: 0 });
  const panel = panelFalso(editor);
  panel.cfg = { nombres_idioma: { en: "English" } };
  assert.equal(VozPanel.prototype._agregar.call(panel, { ...VOZ_IA, picos: [0.1] }, { tipo: "ia", idioma: null, habla: "en" }), true);
  const clip = editor.e.doc.pistas.flatMap((p) => p.clips).find((c) => c.id === editor.e.seleccion);
  assert.equal("idioma" in clip, false);
  assert.match(panel.dichos[0].texto, /^La voz habla English: quedó sonando en todos los idiomas/);
});

// El guard de pago de crear(): ningún POST a urls.voz sin el precio vigente a la vista.
function crearFalso({ estimado, texto = "Hola mundo" }) {
  const pedido = { texto, voz: "Rachel", velocidad: "normal", idioma: "es" };
  const llamadas = { estimar: 0, seguir: [], agregar: [], dichos: [] };
  const falsa = {
    trabajo: null, enviando: false, estimado, maxCaracteres: 3000,
    urls: { voz: "/voz", voz_estimar: "/voz/estimar" },
    editor: { destino: () => "es_CO", enConflicto: () => false },
    texto: { focus() {} },
    _enConflicto: VozPanel.prototype._enConflicto,
    _pedido: () => pedido,
    _pedirEstimado: () => { llamadas.estimar += 1; },
    _pintarCrear() {},
    _decir: (texto, error) => llamadas.dichos.push([texto, error]),
    _detalle() {},
    _pedirJSON: VozPanel.prototype._pedirJSON,
    seguir: (job, encargo) => llamadas.seguir.push([job, encargo]),
    _agregar: (m, opciones) => { llamadas.agregar.push([m, opciones]); return true; },
    cfg: { nombres_idioma: {} },
  };
  return { falsa, llamadas, firma: firmaPedido(pedido) };
}

test("crear(): sin el precio vigente no hay POST a urls.voz; con precio (o gratis) y la firma de ahora, sí", async () => {
  const original = globalThis.fetch;
  const pedidos = [];
  globalThis.fetch = async (url, opciones) => {
    pedidos.push([url, opciones?.method, JSON.parse(opciones?.body ?? "null")]);
    return { ok: true, status: 202, redirected: false, url, headers: { get: () => "application/json" },
             json: async () => ({ job_id: "acme__ed7__voz", clave: "c".repeat(64) }) };
  };
  try {
    const firmaVieja = crearFalso({ estimado: null }).firma.replace("Hola", "Chao");
    const sinPagar = [
      null,                                                    // nunca se pidió el precio
      { firma: "x", calculando: true },
      { firma: null, error: true },                            // el precio no se pudo calcular
      { firma: firmaVieja, precio: "US$ 0,03 aprox." },        // el precio es de otro texto
    ];
    for (const e of sinPagar) {
      const { falsa, llamadas, firma } = crearFalso({ estimado: e });
      if (e && e.firma === null) e.firma = firma;
      if (e?.calculando) e.firma = firma;
      await VozPanel.prototype.crear.call(falsa);
      assert.equal(pedidos.length, 0, JSON.stringify(e));
      assert.equal(llamadas.estimar, 1);                      // en vez de pagar, vuelve a pedir el precio
    }
    for (const vigente of [{ precio: "US$ 0,03 aprox." }, { gratis: true }]) {
      const { falsa, llamadas, firma } = crearFalso({ estimado: null });
      falsa.estimado = { firma, ...vigente };
      await VozPanel.prototype.crear.call(falsa);
      assert.equal(pedidos.length, 1);
      assert.deepEqual(pedidos[0], ["/voz", "POST", { texto: "Hola mundo", voz: "Rachel", velocidad: "normal", idioma: "es" }]);
      assert.deepEqual(llamadas.seguir, [["acme__ed7__voz", { clave: "c".repeat(64), idioma: "es", habla: null }]]);
      pedidos.length = 0;
    }
  } finally {
    globalThis.fetch = original;
  }
});
