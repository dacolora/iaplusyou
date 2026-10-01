// La pestaña «Subtítulos» del editor (capa 5a, Task 7): lo puro de
// subtitulos_modelo.js — qué fuentes se ofrecen, qué archivos pide cada una,
// el estado del idioma, las líneas del listado y los textos del botón.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolver } from "../../static/editor/resolver.js";
import { derivar, palabrasDe } from "../../static/editor/subtitulos_fuente.js";
import {
  alturaDePosicion, claveDeFuente, coloresResaltado, ENCARGO_MAX_MS, encargoGuardado, estadoPanel, estilosPanel, fuenteDeClave,
  fuentePorDefecto, fuentesDisponibles, idiomaPorDefecto, idsSinPalabras, lineaEn, lineasListado, PalabrasPendientes, pedido,
  posicionDeAltura, POSICIONES, resaltadoElegido, respuestaEstimado, textoBoton, textoEstado, textoTiempo,
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

test("fuentesDisponibles: con solo fotos en la principal, «sonido» no está disponible (D11)", () => {
  const doc = docBase();
  for (const c of doc.pistas[0].clips) c.foto = true;
  const sonido = fuentesDisponibles(resuelto(doc), MATS).find((o) => o.clave === "sonido");
  assert.equal(sonido.disponible, false);
  assert.equal(sonido.motivo, "Los videos de esta edición no traen sonido.");
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

test("fuentesDisponibles: las voces del guion (con bloque) no salen como audio suelto; una grabación sí", () => {
  // un borrador automático: un clip de voz por bloque del guion, sin nombre propio
  const doc = docBase();
  const a1 = doc.pistas[2].clips[0];
  doc.pistas[2].clips = [
    { ...a1, id: "b1", material_id: 2, bloque: "gancho", inicio_ms: 0, duracion_ms: 1500 },
    { ...a1, id: "b2", material_id: 3, bloque: "cierre", inicio_ms: 1500, duracion_ms: 1500 },
  ];
  doc.pistas.push({ id: "p_grab", tipo: "audio", bloqueada: false, silenciada: false, oculta: false, clips: [
    { ...a1, id: "g1", material_id: 4, rol_audio: "voz", inicio_ms: 3000, duracion_ms: 1000 },
  ] });
  doc.materiales = [1, 2, 3, 4];
  const mats = { ...MATS, 3: { id: 3, tipo: "audio", duracion_ms: 1500 }, 4: { id: 4, tipo: "audio", nombre: "Grabación 14:32" } };
  const ops = fuentesDisponibles(resuelto(doc), mats);
  assert.deepEqual(ops.map((o) => o.clave), ["voz", "sonido", "material:4"]);
  assert.equal(ops[0].disponible, true);                  // «La voz» cubre los bloques del guion
  assert.equal(ops[2].etiqueta, "Audio «Grabación 14:32»");
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
  assert.equal(textoBoton({ precio: "US$ <0,01 aprox." }), "Generar subtítulos (US$ <0,01 aprox.)");
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

test("encargoGuardado: el de ese trabajo, con su forma y de hace menos de 30 min; si no, null", () => {
  const ahora = 10_000_000;
  const bueno = { job: "acme__ed7__subtitulos", sello: ahora - 60_000, idioma: "es", clave: "voz", ids: [2, "3"] };
  assert.deepEqual(encargoGuardado(bueno, "acme__ed7__subtitulos", ahora), { idioma: "es", clave: "voz", ids: [2, 3] });
  assert.equal(ENCARGO_MAX_MS, 30 * 60 * 1000);
  assert.equal(encargoGuardado({ ...bueno, sello: ahora - ENCARGO_MAX_MS - 1 }, bueno.job, ahora), null);   // viejo
  assert.equal(encargoGuardado({ ...bueno, sello: undefined }, bueno.job, ahora), null);                 // sin sello
  assert.equal(encargoGuardado({ ...bueno, sello: ahora + 120_000 }, bueno.job, ahora), null);            // del futuro
  assert.equal(encargoGuardado(bueno, "otro__ed8__subtitulos", ahora), null);
  assert.equal(encargoGuardado({ ...bueno, idioma: "esp" }, bueno.job, ahora), null);
  assert.equal(encargoGuardado({ ...bueno, clave: "nada" }, bueno.job, ahora), null);
  assert.equal(encargoGuardado({ ...bueno, ids: "2" }, bueno.job, ahora), null);
  assert.equal(encargoGuardado(null, bueno.job, ahora), null);
});

// Revisión final (I1): lo que entra desde la biblioteca trae `tiene_palabras`
// pero no `palabras` (la biblioteca no las manda); sin ellas la vista previa,
// la fila y el listado no derivaban lo que el render sí deriva.
test("idsSinPalabras: los materiales de la edición transcritos en el servidor cuyas palabras no llegaron", () => {
  const doc = docBase();
  doc.pistas.push({ id: "p_voz_2", tipo: "audio", bloqueada: false, silenciada: false, oculta: false, clips: [
    { id: "a2", inicio_ms: 3000, duracion_ms: 1000, material_id: 7, rol_audio: "voz", recorte: { desde_ms: 0, hasta_ms: 1000 },
      velocidad: 1, audio: { volumen: 1 }, por_destino: { es_MX: { material_id: 9 }, en: { material_id: 8 } } },
  ] });
  const mats = {
    1: { id: 1, tipo: "video", tiene_palabras: true },                          // del clon: sin palabras en la página
    2: { id: 2, tipo: "audio", tiene_palabras: true, palabras: [] },            // ya llegaron (vacías también cuentan)
    7: { id: 7, tipo: "audio", tiene_palabras: true },
    8: { id: 8, tipo: "audio", tiene_palabras: false },                         // sin transcribir: no hay nada que traer
    9: { id: 9, tipo: "audio", tiene_palabras: true },                          // alternativa por destino
    40: { id: 40, tipo: "audio", tiene_palabras: true },                        // en la página pero fuera de la edición
  };
  assert.deepEqual(idsSinPalabras(doc, mats), [1, 7, 9]);
  assert.deepEqual(idsSinPalabras(doc, mats, [7, 1]), [9]);                     // lo que ya se pide no se repite
  assert.deepEqual(idsSinPalabras(doc, {}), []);                                // material desconocido: nada
  assert.deepEqual(idsSinPalabras(null, mats), []);
});

test("PalabrasPendientes: pide cada id una vez, aunque se revise mientras viaja, y suma lo que llega", async () => {
  const doc = docBase();
  let mats = { 1: { id: 1, tipo: "video", tiene_palabras: true }, 2: { id: 2, tipo: "audio", tiene_palabras: true } };
  const pedidos = [];
  let soltar;
  const agregados = [];
  const pp = new PalabrasPendientes({
    pedir: (ids) => {
      pedidos.push(ids);
      return new Promise((r) => { soltar = r; });
    },
    agregar: (mapa) => {
      agregados.push(mapa);
      mats = { ...mats, ...mapa };
      pp.revisar(doc, mats);                                       // el aviso «materiales» vuelve a revisar
    },
  });
  const primero = pp.revisar(doc, mats);
  pp.revisar(doc, mats);                                           // mientras viaja: no se pide otra vez
  assert.deepEqual(pedidos, [[1, 2]]);
  soltar({ 1: { id: 1, tiene_palabras: true, palabras: [{ t_ms: 0, dur_ms: 300, texto: "hola" }] },
           2: { id: 2, tiene_palabras: true } });                  // el 2 no las trajo: no se vuelve a pedir en bucle
  await primero;
  assert.equal(agregados.length, 1);
  pp.revisar(doc, mats);
  assert.deepEqual(pedidos, [[1, 2]]);
});

test("PalabrasPendientes: si el pedido falla, la próxima revisión lo intenta de nuevo", async () => {
  const doc = docBase();
  const mats = { 2: { id: 2, tipo: "audio", tiene_palabras: true } };
  const pedidos = [];
  let falla = true;
  const pp = new PalabrasPendientes({
    pedir: async (ids) => {
      pedidos.push(ids);
      if (falla) throw new Error("sin conexión");
      return { 2: { id: 2, tiene_palabras: true, palabras: [] } };
    },
    agregar: () => {},
  });
  await pp.revisar(doc, mats);
  falla = false;
  await pp.revisar(doc, mats);
  assert.deepEqual(pedidos, [[2], [2]]);
  await pp.revisar(doc, mats);                                     // ya llegó: no se pide más
  assert.equal(pedidos.length, 2);
});

// Revisión final (m9): un archivo sin duración da «precio no disponible»
// (usd null): el botón queda apagado con ese texto — ni gratis, ni un error
// que se reintenta, ni un clic que transcriba.
test("respuestaEstimado: gratis, precio, sin precio o error", () => {
  assert.deepEqual(respuestaEstimado(true, { gratis: true, usd: 0, precio: "" }), { gratis: true });
  assert.deepEqual(respuestaEstimado(true, { gratis: false, usd: 0.003, precio: "US$ <0,01 aprox." }),
    { precio: "US$ <0,01 aprox." });
  assert.deepEqual(respuestaEstimado(true, { gratis: false, usd: null, precio: "precio no disponible" }),
    { sinPrecio: true, precio: "precio no disponible" });
  assert.deepEqual(respuestaEstimado(true, { gratis: false, usd: null, precio: "" }), { error: true });
  assert.deepEqual(respuestaEstimado(false, { error: "x" }), { error: true });
  assert.deepEqual(respuestaEstimado(true, null), { error: true });
  assert.deepEqual(respuestaEstimado(true, [1]), { error: true });
});
