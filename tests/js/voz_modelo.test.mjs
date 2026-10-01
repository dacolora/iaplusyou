// La voz en off de la pestaña «Audio» (capa 5a, Task 8): lo puro de
// voz_modelo.js — con qué formato graba cada navegador, el reloj, por qué no
// se puede grabar, el estado del texto, el filtro de voces, el idioma inicial,
// el botón «Crear la voz», lo que se guarda para retomar tras recargar y lo
// que se dice al agregar la voz.
import { test } from "node:test";
import assert from "node:assert/strict";
import { ponerTextos } from "../../static/editor/textos.js";
import {
  avisoAgregada, botonCrear, elegirGrabacion, encargoVozGuardado, ENCARGO_VOZ_MAX_MS, estadoTexto, filtrarVoces, FILTROS_VOZ,
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
  assert.deepEqual(encargoVozGuardado(bueno, "acme__ed7__voz", ahora), { clave, idioma: "es" });
  assert.deepEqual(encargoVozGuardado({ ...bueno, idioma: null }, "acme__ed7__voz", ahora), { clave, idioma: null });
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
