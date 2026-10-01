// La pestaña «Subtítulos» del editor (capa 5a, Task 7): lo puro de
// subtitulos_modelo.js — qué fuentes se ofrecen, qué archivos pide cada una,
// el estado del idioma, las líneas del listado y los textos del botón.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolver } from "../../static/editor/resolver.js";
import { derivar, palabrasDe } from "../../static/editor/subtitulos_fuente.js";
import {
  alturaDePosicion, claveDeFuente, coloresResaltado, estadoPanel, estilosPanel, fuenteDeClave, fuentePorDefecto,
  fuentesDisponibles, idiomaPorDefecto, lineaEn, lineasListado, pedido, posicionDeAltura, POSICIONES, resaltadoElegido,
  textoBoton, textoEstado, textoTiempo,
} from "../../static/editor/subtitulos_modelo.js";
import { ponerTextos } from "../../static/editor/textos.js";
import { docBase } from "./doc_base.mjs";

const ESTILOS = JSON.parse(readFileSync(new URL("../fixtures/subtitulos_eventos_casos.json", import.meta.url), "utf8")).estilos;

// docBase: principal con dos clips del clon (material 1), la voz a1
// (material 2, rol voz) y el sonido de la escena espejo (p_sonido).
const MATS = {
  1: { id: 1, tipo: "video", tiene_audio: true, duracion_ms: 8000 },
  2: { id: 2, tipo: "audio", nombre: "Voz del guion", duracion_ms: 3000 },
};

function resuelto(doc = docBase(), idioma = "es", pais = "CO") {
  return resolver(doc, idioma, pais);
}

test("fuentesDisponibles: la voz, el sonido del video y un audio por material, con su nombre", () => {
  const ops = fuentesDisponibles(resuelto(), MATS);
  assert.deepEqual(ops.map((o) => [o.clave, o.disponible, o.motivo]), [
    ["voz", true, null], ["sonido", true, null], ["material:2", true, null],
  ]);
  assert.deepEqual(ops.map((o) => o.etiqueta), ["La voz", "El sonido del video", "Audio «Voz del guion»"]);
});

test("fuentesDisponibles: sin voz en este destino, la voz no se puede elegir y dice por qué", () => {
  const doc = docBase();
  doc.pistas[2].clips[0].idioma = "en";          // la voz habla en inglés: en es_CO se quita (D10)
  const ops = fuentesDisponibles(resuelto(doc), MATS);
  const voz = ops.find((o) => o.clave === "voz");
  assert.equal(voz.disponible, false);
  assert.equal(voz.motivo, "No hay voz en este destino.");
  assert.equal(ops.some((o) => o.clave === "material:2"), false);
});

test("fuentesDisponibles: un video mudo no ofrece su sonido (uno sin medir, sí)", () => {
  const mudo = { ...MATS, 1: { ...MATS[1], tiene_audio: false } };
  const sonido = fuentesDisponibles(resuelto(), mudo).find((o) => o.clave === "sonido");
  assert.equal(sonido.disponible, false);
  assert.equal(sonido.motivo, "Los videos de esta edición no traen sonido.");
  const sinMedir = { ...MATS, 1: { ...MATS[1], tiene_audio: null } };
  assert.equal(fuentesDisponibles(resuelto(), sinMedir).find((o) => o.clave === "sonido").disponible, true);
});

test("fuentesDisponibles: dos clips del mismo audio dan UNA opción; sin nombre, el de su fila", () => {
  const doc = docBase();
  const a1 = doc.pistas[2].clips[0];
  doc.pistas.push({ id: "p_musica", tipo: "audio", bloqueada: false, silenciada: false, oculta: false, clips: [
    { ...a1, id: "m1", material_id: 3, rol_audio: "musica", inicio_ms: 0 },
    { ...a1, id: "m2", material_id: 3, rol_audio: "musica", inicio_ms: 4000 },
  ] });
  doc.materiales = [1, 2, 3];
  const mats = { ...MATS, 3: { id: 3, tipo: "audio", duracion_ms: 3000 } };
  const audios = fuentesDisponibles(resuelto(doc), mats).filter((o) => o.clave.startsWith("material:"));
  assert.deepEqual(audios.map((o) => o.clave), ["material:2", "material:3"]);
  assert.equal(audios[1].etiqueta, "Audio «Música»");
});

test("fuentesDisponibles: una pista silenciada u oculta no se ofrece", () => {
  const doc = docBase();
  doc.pistas[2].silenciada = true;
  const ops = fuentesDisponibles(resuelto(doc), MATS);
  assert.equal(ops.find((o) => o.clave === "voz").disponible, false);
  assert.equal(ops.some((o) => o.clave === "material:2"), false);
});

test("claveDeFuente y fuenteDeClave van y vuelven; lo que no es una fuente da null", () => {
  for (const f of [{ tipo: "voz" }, { tipo: "sonido" }, { tipo: "material", material_id: 42 }]) {
    assert.deepEqual(fuenteDeClave(claveDeFuente(f)), f);
  }
  assert.equal(claveDeFuente({ tipo: "material", material_id: 7 }), "material:7");
  for (const mala of [null, "", "otra", "material:", "material:0", "material:x", "material:-3"]) {
    assert.equal(fuenteDeClave(mala), null, String(mala));
  }
});

test("pedido: separa lo que falta transcribir, lo mudo y lo que solo hay que traer", () => {
  const r = resuelto();
  assert.deepEqual(pedido(r, "voz", MATS), { todos: [2], faltan: [2], mudos: [], cargar: [] });
  const transcrita = { ...MATS, 2: { ...MATS[2], tiene_palabras: true } };
  assert.deepEqual(pedido(r, "voz", transcrita), { todos: [2], faltan: [], mudos: [], cargar: [2] });
  const conPalabras = { ...MATS, 2: { ...MATS[2], palabras: [] } };          // vacía = hecha (música sin letra)
  assert.deepEqual(pedido(r, "voz", conPalabras), { todos: [2], faltan: [], mudos: [], cargar: [] });
  const mudo = { ...MATS, 1: { ...MATS[1], tiene_audio: false } };
  assert.deepEqual(pedido(r, "sonido", mudo), { todos: [1], faltan: [], mudos: [1], cargar: [] });
  assert.deepEqual(pedido(r, "sonido", MATS), { todos: [1], faltan: [1], mudos: [], cargar: [] });
  assert.deepEqual(pedido(r, "nada", MATS), { todos: [], faltan: [], mudos: [], cargar: [] });
  assert.deepEqual(pedido(null, "voz", MATS), { todos: [], faltan: [], mudos: [], cargar: [] });
});

test("estadoPanel: ausente con palabras guardadas es legado; sin nada, ninguno", () => {
  const doc = docBase();
  doc.subtitulos.palabras = { es_CO: [{ t_ms: 0, dur_ms: 300, texto: "Hola" }, { t_ms: 300, dur_ms: 300, texto: "mundo" }] };
  assert.deepEqual(estadoPanel(doc, resuelto(doc)), { tipo: "legado", clave: null, n: 2 });
  assert.deepEqual(estadoPanel(docBase(), resuelto()), { tipo: "ninguno", clave: null, n: 0 });
  // otro destino sin palabras guardadas: ninguno
  assert.deepEqual(estadoPanel(doc, resuelto(doc, "en", "US")), { tipo: "ninguno", clave: null, n: 0 });
});

test("estadoPanel: [] es quitados (gana sobre las palabras guardadas); con fuentes, derivados con n", () => {
  const doc = docBase();
  doc.subtitulos.palabras = { es_CO: [{ t_ms: 0, dur_ms: 300, texto: "Hola" }] };
  doc.subtitulos.fuentes = { es: [] };
  assert.deepEqual(estadoPanel(doc, resuelto(doc)), { tipo: "quitados", clave: null, n: 0 });
  doc.subtitulos.fuentes = { es: [{ tipo: "voz" }] };
  const mats = { ...MATS, 2: { ...MATS[2], palabras: [{ t_ms: 0, dur_ms: 300, texto: "Hola" }, { t_ms: 400, dur_ms: 300, texto: "otra" }] } };
  assert.deepEqual(estadoPanel(doc, resuelto(doc), palabrasDe(mats)), { tipo: "derivados", clave: "voz", n: 2 });
  doc.subtitulos.fuentes = { es: [{ tipo: "material", material_id: 2 }] };
  assert.equal(estadoPanel(doc, resuelto(doc), palabrasDe(mats)).clave, "material:2");
  // sin el mapa de palabras: las del resuelto (ya derivado por la vista)
  const r = { ...resuelto(doc), subtitulos: { ...resuelto(doc).subtitulos, palabras: [{ t_ms: 0, dur_ms: 1, texto: "x" }] } };
  assert.equal(estadoPanel(doc, r).n, 1);
});

test("textoEstado: una frase por estado, con el nombre del audio y el número de palabras", () => {
  assert.equal(textoEstado({ tipo: "ninguno", n: 0 }), "Este idioma todavía no tiene subtítulos.");
  assert.match(textoEstado({ tipo: "legado", n: 3 }), /^Estos subtítulos vienen del borrador automático/);
  assert.equal(textoEstado({ tipo: "quitados", n: 0 }), "Quitaste los subtítulos de este idioma.");
  assert.equal(textoEstado({ tipo: "derivados", clave: "voz", n: 12 }), "Subtítulos de la voz · 12 palabras.");
  assert.equal(textoEstado({ tipo: "derivados", clave: "sonido", n: 4 }), "Subtítulos del sonido del video · 4 palabras.");
  assert.equal(textoEstado({ tipo: "derivados", clave: "material:2", n: 7 }, MATS), "Subtítulos de «Voz del guion» · 7 palabras.");
  assert.equal(textoEstado({ tipo: "derivados", clave: "material:9", n: 3 }, MATS), "Subtítulos de «Audio» · 3 palabras.");
});

// Seis palabras de la voz (material 2), la tercera corregida.
const ORIGINALES = [
  { t_ms: 0, dur_ms: 300, texto: "Hola" }, { t_ms: 300, dur_ms: 300, texto: "a" }, { t_ms: 600, dur_ms: 300, texto: "krea" },
  { t_ms: 900, dur_ms: 300, texto: "tiv" }, { t_ms: 1200, dur_ms: 300, texto: "que" }, { t_ms: 1500, dur_ms: 300, texto: "tal" },
];

test("lineasListado: de a 4 palabras, marca las corregidas con lo que se oyó", () => {
  const derivadas = ORIGINALES.map((w, indice) => ({ ...w, texto: indice === 2 ? "Creatv" : w.texto, material_id: 2, indice, clip_id: "a1" }));
  const lineas = lineasListado(derivadas, { 2: { palabras: ORIGINALES } });
  assert.deepEqual(lineas.map((l) => [l.t_ms, l.dur_ms, l.palabras.map((p) => p.texto)]), [
    [0, 1200, ["Hola", "a", "Creatv", "tiv"]], [1200, 600, ["que", "tal"]],
  ]);
  assert.deepEqual(lineas[0].palabras[2], { texto: "Creatv", material_id: 2, indice: 2, corregida: true, original: "krea" });
  assert.deepEqual(lineas[0].palabras[0], { texto: "Hola", material_id: 2, indice: 0, corregida: false, original: "Hola" });
});

test("lineasListado: una línea se cierra antes de pasar de 22 caracteres", () => {
  const largas = ["Extraordinario", "nuevo", "producto", "hoy"].map((texto, i) => ({ t_ms: i * 200, dur_ms: 200, texto, material_id: 5, indice: i }));
  const lineas = lineasListado(largas, {});
  assert.deepEqual(lineas.map((l) => l.palabras.map((p) => p.texto)), [["Extraordinario", "nuevo"], ["producto", "hoy"]]);
  // sin la transcripción del material a mano: no se puede decir que esté corregida
  assert.deepEqual(lineas[0].palabras[0], { texto: "Extraordinario", material_id: 5, indice: 0, corregida: false, original: null });
});

test("lineasListado: palabras de legado (sin material) también se agrupan, de solo lectura", () => {
  const lineas = lineasListado([{ t_ms: 0, dur_ms: 300, texto: "Hola" }, { t_ms: 300, dur_ms: 300, texto: "mundo" }], {});
  assert.deepEqual(lineas, [{ t_ms: 0, dur_ms: 600, palabras: [
    { texto: "Hola", material_id: null, indice: null, corregida: false, original: null },
    { texto: "mundo", material_id: null, indice: null, corregida: false, original: null },
  ] }]);
});

test("lineasListado: lo que da derivar entra tal cual (paridad con la vista previa)", () => {
  const doc = docBase();
  doc.subtitulos.fuentes = { es: [{ tipo: "voz" }] };
  doc.subtitulos.correcciones = { 2: { 1: "y" } };
  const mats = { ...MATS, 2: { ...MATS[2], palabras: ORIGINALES.slice(0, 3) } };
  const lineas = lineasListado(derivar(resuelto(doc), palabrasDe(mats)), mats);
  assert.deepEqual(lineas[0].palabras.map((p) => [p.texto, p.corregida]), [["Hola", false], ["y", true], ["krea", false]]);
});

test("lineaEn: [t, t + dur) — en el borde de entrada sí, en el de salida no", () => {
  const lineas = [{ t_ms: 1000, dur_ms: 1000, palabras: [] }, { t_ms: 2500, dur_ms: 500, palabras: [] }];
  assert.equal(lineaEn(lineas, 999), -1);
  assert.equal(lineaEn(lineas, 1000), 0);
  assert.equal(lineaEn(lineas, 1999), 0);
  assert.equal(lineaEn(lineas, 2000), -1);
  assert.equal(lineaEn(lineas, 2500), 1);
  assert.equal(lineaEn(lineas, 3000), -1);
  assert.equal(lineaEn([], 0), -1);
});

test("textoBoton: corriendo, calculando, error, gratis y con precio (tal cual llega)", () => {
  assert.equal(textoBoton({ corriendo: true, etapa: "Transcribiendo" }), "Generando los subtítulos… Transcribiendo");
  assert.equal(textoBoton({ corriendo: true }), "Generando los subtítulos…");
  assert.equal(textoBoton({ calculando: true, precio: "US$ <0,01 aprox." }), "Calculando el precio…");
  assert.equal(textoBoton({ error: true }), "No se pudo calcular el precio: vuelve a intentar.");
  assert.equal(textoBoton({ gratis: true }), "Generar subtítulos (gratis)");
  assert.equal(textoBoton({ precio: "US$ <0,01 aprox." }), "Generar subtítulos ≈ US$ <0,01 aprox.");
});

test("textoTiempo: m:ss y décimas con el separador del idioma", () => {
  assert.equal(textoTiempo(3200), "0:03,2");
  assert.equal(textoTiempo(0), "0:00,0");
  assert.equal(textoTiempo(63_990), "1:03,9");       // nunca «0:60,0»: las décimas se cortan
  assert.equal(textoTiempo(-5), "0:00,0");
  ponerTextos({}, "en");
  try {
    assert.equal(textoTiempo(3200), "0:03.2");
  } finally {
    ponerTextos({}, "es");
  }
});

test("idiomaPorDefecto: el del destino si se puede transcribir; si no, el primero", () => {
  assert.equal(idiomaPorDefecto("es_CO", ["es", "en", "pt"]), "es");
  assert.equal(idiomaPorDefecto("pt_BR", ["es", "en", "pt"]), "pt");
  assert.equal(idiomaPorDefecto("ja_JP", ["es", "en"]), "es");
  assert.equal(idiomaPorDefecto(null, []), null);
});

test("fuentePorDefecto: la que eligió la persona, si no la vigente, si no la primera que se puede", () => {
  const ops = [{ clave: "voz", disponible: false }, { clave: "sonido", disponible: true }, { clave: "material:2", disponible: true }];
  assert.equal(fuentePorDefecto(ops, { tipo: "ninguno" }, null), "sonido");
  assert.equal(fuentePorDefecto(ops, { tipo: "derivados", clave: "material:2" }, null), "material:2");
  assert.equal(fuentePorDefecto(ops, { tipo: "derivados", clave: "material:2" }, "sonido"), "sonido");
  assert.equal(fuentePorDefecto(ops, { tipo: "ninguno" }, "voz"), "sonido");          // ya no se puede: otra
  assert.equal(fuentePorDefecto([{ clave: "voz", disponible: false }], { tipo: "ninguno" }, null), null);
});

test("estilosPanel: los cuatro estilos en orden, con su nombre y si resaltan", () => {
  assert.deepEqual(estilosPanel(ESTILOS), [
    { id: "karaoke", nombre: "Karaoke", resalta: true },
    { id: "caja", nombre: "Caja", resalta: false },
    { id: "palabra_grande", nombre: "Palabra grande", resalta: true },
    { id: "minimal", nombre: "Mínimo", resalta: false },
  ]);
});

test("coloresResaltado: amarillo, verde, blanco y el de la marca (si es un color)", () => {
  const doc = docBase();
  assert.deepEqual(coloresResaltado(doc).map((c) => [c.color, c.nombre]), [
    ["#FFD400", "Amarillo"], ["#3DDC84", "Verde"], ["#FFFFFF", "Blanco"], ["#7C3AED", "Color de marca"],
  ]);
  doc.marca.color = null;
  assert.equal(coloresResaltado(doc).length, 3);
});

test("resaltadoElegido: el del documento, o el del estilo; null en un estilo que no resalta", () => {
  assert.equal(resaltadoElegido({ estilo_id: "karaoke" }, ESTILOS), "#FFD400");
  assert.equal(resaltadoElegido({ estilo_id: "karaoke", resaltado: "#3DDC84" }, ESTILOS), "#3DDC84");
  assert.equal(resaltadoElegido({ estilo_id: "caja", resaltado: "#3DDC84" }, ESTILOS), null);
  assert.equal(resaltadoElegido({ estilo_id: "raro" }, ESTILOS), "#FFD400");            // desconocido: karaoke
});

test("altura: más alto en el deslizador = más arriba en el video; los atajos caen en su lugar", () => {
  assert.equal(alturaDePosicion(0.78), 22);
  assert.equal(alturaDePosicion(0.2), 80);
  assert.equal(posicionDeAltura(50), 0.5);
  assert.equal(posicionDeAltura(90), 0.1);
  assert.deepEqual(POSICIONES.map((p) => p.valor), [0.2, 0.5, 0.78]);
  assert.equal(alturaDePosicion(undefined), 22);                                  // sin posición: la de siempre (0,78)
});
