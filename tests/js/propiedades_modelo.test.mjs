// El panel de propiedades (capa 4b, Task 7): lo puro de propiedades_modelo.js
// — qué formulario toca a lo elegido, los valores que muestra y los cambios
// que pide. La clase `Propiedades` (propiedades.js) es DOM y no corre en Node;
// importarla sí (modulos_navegador.test.mjs).
import { test } from "node:test";
import assert from "node:assert/strict";
import * as op from "../../static/editor/operaciones.js";
import {
  alternarSilencio, cambioContorno, cambioFondo, cambioGrosor, cambioLlenar, cambioSombra, claveForma,
  COLORES, escalaDePorcentaje, formaDe, mensajeConflicto, mensajeRechazo, modelo, motivoRechazo, textoPorcentaje,
  textoSegundos, textoVelocidad, TRANSICION_MS,
} from "../../static/editor/propiedades_modelo.js";
import { docBase } from "./doc_base.mjs";

const INFO = { 1: { duracion_ms: 8000, tiene_audio: true }, 2: { duracion_ms: 3000 }, 3: { duracion_ms: 1500, tiene_audio: false } };
const IMAGEN = { id: 4, tipo: "imagen", ancho: 600, alto: 400 };
const clipDe = (d, id) => d.pistas.flatMap((p) => p.clips).find((c) => c.id === id);

// docBase + una imagen, una música y un texto «Título»; devuelve el doc y los ids nuevos.
function docCompleto() {
  const conImagen = op.agregarImagen(docBase(), IMAGEN, 0, {}, INFO);
  const conMusica = op.agregarAudio(conImagen.doc, { id: 2 }, 0, { rol: "musica" }, INFO);
  const conTexto = op.agregarTexto(conMusica.doc, 4000, "titulo", {}, INFO);
  return { doc: conTexto.doc, imagen: conImagen.seleccion, musica: conMusica.seleccion, titulo: conTexto.seleccion };
}

test("formaDe: un formulario por clase de clip; nada elegido (o algo que ya no está) es la edición entera", () => {
  const { doc, imagen, musica, titulo } = docCompleto();
  assert.equal(formaDe(doc, null), "documento");
  assert.equal(formaDe(doc, "no-existe"), "documento");
  assert.equal(formaDe(doc, "v0"), "video");
  assert.equal(formaDe(doc, titulo), "texto");
  assert.equal(formaDe(doc, "t1"), "texto");
  assert.equal(formaDe(doc, imagen), "imagen");
  assert.equal(formaDe(doc, musica), "audio");
  assert.equal(formaDe(doc, "a1"), "audio");               // la voz
  assert.equal(formaDe(doc, "s_v0"), "sonido");            // el espejo: no se edita aquí
  assert.equal(formaDe(docBase(), "s0"), "sonido");         // también el del borrador (s0, s1…)
  const pip = docBase();
  pip.pistas.push({ id: "p_pip", tipo: "superpuesto", clips: [{ id: "pip1", inicio_ms: 0, duracion_ms: 1000, material_id: 1 }] });
  assert.equal(formaDe(pip, "pip1"), "otro");
});

test("modelo sin nada elegido: la mezcla de la edición y qué hacer", () => {
  const d = docBase();
  const m = modelo(d, null);
  assert.equal(m.forma, "documento");
  assert.equal(m.ayuda, "Elige algo en la línea de tiempo o en el video para cambiarlo.");
  assert.equal(m.mezcla, "equilibrada");
  assert.equal(m.aMedida, false);
  assert.deepEqual(m.opcionesMezcla.map((o) => [o.valor, o.texto]),
    [["equilibrada", "Equilibrada"], ["voz_protagonista", "Voz primero"], ["ambiente_protagonista", "Ambiente primero"]]);
  assert.ok(m.opcionesMezcla.every((o) => o.ayuda));
  d.mezcla = { preset: "voz_protagonista", volumenes: { musica: 0.1, voz: null } };
  assert.equal(modelo(d, null).mezcla, "voz_protagonista");
  assert.equal(modelo(d, null).aMedida, true);             // hay volúmenes a medida: elegir una mezcla los quita
  d.mezcla = { preset: "rara", volumenes: { voz: null } };
  assert.equal(modelo(d, null).mezcla, "equilibrada");
  assert.equal(modelo(d, null).aMedida, false);
  assert.equal(claveForma(modelo(d, null)), "documento:");
});

test("modelo de un video: velocidad, sonido de la escena, zoom lento, transición y borrar", () => {
  const d = docBase();
  const m = modelo(d, "v0", { info: INFO });
  assert.equal(m.forma, "video");
  assert.equal(m.clipId, "v0");
  assert.equal(claveForma(m), "video:v0");
  assert.equal(m.velocidad, 1);
  assert.deepEqual(m.velocidades.map((v) => v.texto), ["0,5×", "0,75×", "1×", "1,25×", "1,5×", "2×"]);
  // docBase trae los espejos del borrador (s0, s1): el sonido se puede cambiar igual
  assert.deepEqual(m.sonido, { disponible: true, porcentaje: 100, motivo: null });
  assert.equal(m.kenBurns, "in");
  assert.equal(modelo(d, "v1", { info: INFO }).kenBurns, "out");
  assert.deepEqual(m.transicion, { disponible: true, motivo: null, tipo: "corte", duracionMs: TRANSICION_MS.defecto,
    min: 200, max: 1500, paso: 100, ayuda: "Junta los dos clips: el video queda tan corto como dure la transición." });
  assert.deepEqual(m.transiciones.map((t) => t.texto), ["Corte", "Fundido", "Deslizar", "Zoom", "Fundido a negro"]);
  assert.equal(m.puedeBorrar, true);
  // el último video no tiene transición hacia el siguiente
  const ultimo = modelo(d, "v1", { info: INFO }).transicion;
  assert.equal(ultimo.disponible, false);
  assert.match(ultimo.motivo, /último/);
  // lo que ya tiene
  const conSonido = op.volumenSonido(d, "v0", 0.35, INFO).doc;
  assert.equal(modelo(conSonido, "v0", { info: INFO }).sonido.porcentaje, 35);
  const recortado = op.recortar(docBase(), "v0", "fin", -1000, INFO).doc;           // v0 deja 1 s de cola
  const conTr = op.ponerTransicion(recortado, "v0", "zoom", 700, INFO).doc;
  assert.equal(modelo(conTr, "v0", { info: INFO }).transicion.tipo, "zoom");
  assert.equal(modelo(conTr, "v0", { info: INFO }).transicion.duracionMs, 700);
  assert.equal(modelo(op.cambiar(d, "v0", { ken_burns: null }, INFO).doc, "v0", { info: INFO }).kenBurns, null);
});

test("modelo de un video sin sonido que cambiar dice por qué; con un solo video no se puede borrar", () => {
  const lento = op.cambiarVelocidad(docBase(), "v0", 0.5, INFO).doc;
  const m = modelo(lento, "v0", { info: INFO });
  assert.equal(m.velocidad, 0.5);
  assert.equal(m.sonido.disponible, false);
  assert.match(m.sonido.motivo, /velocidad/);
  const mudo = op.agregarVideo(docBase(), { id: 3 }, {}, INFO);
  const m3 = modelo(mudo.doc, mudo.seleccion, { info: INFO });
  assert.equal(m3.sonido.disponible, false);
  assert.match(m3.sonido.motivo, /no trae sonido/);
  const solo = op.borrar(docBase(), "v1", INFO).doc;
  const m1 = modelo(solo, "v0", { info: INFO });
  assert.equal(m1.puedeBorrar, false);
  assert.match(m1.motivoBorrar, /al menos un clip de video/);
});

test("modelo de un texto: el texto del destino, fuente, tamaño en px, color con la marca, contorno, sombra, fondo…", () => {
  const { doc, titulo } = docCompleto();
  const m = modelo(doc, titulo, { destino: "es_CO", info: INFO });
  assert.equal(m.forma, "texto");
  assert.deepEqual(m.texto, { valor: "Escribe aquí", editable: true, destino: "es_CO", nota: null });
  assert.equal(m.fuente, "Inter-Bold");
  assert.deepEqual(m.fuentes, [], "sin el catálogo de la página no hay fuentes que ofrecer");
  assert.deepEqual(m.tamano, { px: 72, min: 12, max: 200 });
  assert.equal(m.color, "#FFFFFF");
  // la paleta: blanco, negro, el color de marca, amarillo y rojo; marcado el que tiene
  assert.deepEqual(m.paleta.map((c) => c.nombre), ["Blanco", "Negro", "Color de marca", "Amarillo", "Rojo"]);
  assert.equal(m.paleta[2].color, "#7C3AED");
  assert.deepEqual(m.paleta.filter((c) => c.elegido).map((c) => c.nombre), ["Blanco"]);
  assert.deepEqual(m.contorno, { activo: true, color: "#000000", grosorPx: 4, min: 1, max: 20 });
  assert.deepEqual(m.sombra, { activo: false });
  assert.deepEqual(m.fondo, { tipo: "ninguno", color: "#000000", opacidad: 80 });
  assert.equal(m.alineacion, "centro");
  assert.equal(m.animacion, "ninguna");
  assert.deepEqual(m.centrado, { x: true, y: false });     // el título entra arriba (y = 0.2)
  // el precio entra en píldora del color de marca; el llamado, en caja blanca
  const precio = op.agregarTexto(docBase(), 0, "precio", {}, INFO);
  assert.deepEqual(modelo(precio.doc, precio.seleccion).fondo, { tipo: "pildora", color: "#7C3AED", opacidad: 100 });
  const llamado = op.agregarTexto(docBase(), 0, "llamado", {}, INFO);
  assert.deepEqual(modelo(llamado.doc, llamado.seleccion).fondo, { tipo: "caja", color: "#FFFFFF", opacidad: 90 });
  assert.equal(modelo(llamado.doc, llamado.seleccion).paleta.find((c) => c.elegido).nombre, "Negro");
  const sub = op.agregarTexto(docBase(), 0, "subtitulo", {}, INFO);
  assert.deepEqual(modelo(sub.doc, sub.seleccion).sombra, { activo: true });
  // un texto con lo mínimo (el de docBase): los valores por defecto del documento
  const t1 = modelo(docBase(), "t1");
  assert.deepEqual(t1.tamano, { px: 77, min: 12, max: 200 });      // 0.04 × 1920
  assert.equal(t1.color, "#FFFFFF");
  assert.equal(t1.contorno.activo, false);
  assert.equal(t1.texto.destino, "es");                            // sin destino: el idioma base
});

test("modelo de un texto variable: el valor del destino (o el del idioma) y lo que se escribe vale para ese destino", () => {
  const d = docBase();
  d.pistas[1].clips[0].texto = { variable: "gancho" };
  d.variables.textos.gancho = { es: "Hola", es_MX: "Qué onda" };
  assert.equal(modelo(d, "t1", { destino: "es_MX" }).texto.valor, "Qué onda");
  const co = modelo(d, "t1", { destino: "es_CO" }).texto;
  assert.equal(co.valor, "Hola");
  assert.equal(co.editable, true);
  assert.match(co.nota, /es · CO/);
  assert.equal(modelo(d, "t1", { destino: "en_US" }).texto.valor, "");      // sin traducir todavía
  // el precio sale de cada país: no se escribe
  d.pistas[1].clips[0].texto = { variable: "precio" };
  d.variables.precios = { es_CO: 49900 };
  const p = modelo(d, "t1", { destino: "es_CO" }).texto;
  assert.equal(p.editable, false);
  assert.match(p.valor, /49/);
  assert.match(p.nota, /precio/);
  assert.equal(modelo(d, "t1", { destino: "es_MX" }).texto.valor, "Precio");
});

test("modelo de una imagen: tamaño en % del ancho de la pantalla, opacidad, llenar y centrar", () => {
  const { doc, imagen } = docCompleto();
  const m = modelo(doc, imagen, { materiales: { 4: IMAGEN } });
  assert.equal(m.forma, "imagen");
  assert.deepEqual(m.tamano, { porcentaje: 60, min: 3, max: 277 });          // entra al 60 % del ancho; 0.05…5 × 600/1080
  assert.equal(m.opacidad, 100);
  assert.equal(m.centrada, true);
  assert.equal(m.llena, false);
  assert.equal(m.llenar.alcanza, true);
  const lleno = op.cambiar(doc, imagen, cambioLlenar(clipDe(doc, imagen), IMAGEN, doc.formato), INFO).doc;
  assert.equal(modelo(lleno, imagen, { materiales: { 4: IMAGEN } }).llena, true);
  // una imagen chiquita no llega a llenar (la escala tiene tope 5): se dice
  const chica = { id: 5, tipo: "imagen", ancho: 100, alto: 100 };
  const r = op.agregarImagen(docBase(), chica, 0, {}, INFO);
  assert.equal(modelo(r.doc, r.seleccion, { materiales: { 5: chica } }).llenar.alcanza, false);
});

test("modelo de un audio: volumen, fundidos con tope, silencio y la voz que cambia por país", () => {
  const { doc, musica } = docCompleto();
  const m = modelo(doc, musica, { info: INFO });
  assert.equal(m.forma, "audio");
  assert.equal(m.nombre, "Música");
  assert.equal(m.volumen, 100);
  assert.equal(m.silenciado, false);
  assert.deepEqual(m.fundidos, { entradaMs: 0, salidaMs: 1000, max: 1500, paso: 100 });   // la mitad de 3 s
  assert.equal(m.nota, null);
  const callada = op.cambiar(doc, musica, { audio: { volumen: 0 } }, INFO).doc;
  assert.equal(modelo(callada, musica).silenciado, true);
  const voz = modelo(doc, "a1");
  assert.equal(voz.nombre, "Voz");
  assert.equal(voz.nota, null);
  doc.pistas.find((p) => p.id === "p_voz").clips[0].por_destino = { es_CO: { material_id: 2, duracion_ms: 3000 } };
  assert.equal(modelo(doc, "a1").nota, "La voz se ajusta sola a cada país.");
});

test("modelo del sonido de la escena: se cambia desde su video", () => {
  const d = op.normalizar(docBase(), INFO);
  assert.deepEqual(modelo(d, "s_v1"), { forma: "sonido", clipId: "s_v1", principalId: "v1" });
  assert.equal(modelo(docBase(), "s1").principalId, "v1");        // espejo del borrador: por su lugar
});

test("cambios de estilo que pide el panel: contorno, grosor, sombra y fondo en fracciones del lienzo", () => {
  assert.deepEqual(cambioContorno(true, "9:16"), { estilo: { contorno: { color: "#000000", grosor: 4 / 1920 } } });
  assert.deepEqual(cambioContorno(false, "9:16"), { estilo: { contorno: null } });
  assert.deepEqual(cambioGrosor(8, "9:16"), { estilo: { contorno: { grosor: 8 / 1920 } } });
  assert.deepEqual(cambioGrosor(8, "16:9"), { estilo: { contorno: { grosor: 8 / 1080 } } });
  assert.deepEqual(cambioSombra(true, "9:16"), { estilo: { sombra: { color: "#000000", dx: 3 / 1920, dy: 3 / 1920 } } });
  assert.deepEqual(cambioSombra(false, "9:16"), { estilo: { sombra: null } });
  assert.deepEqual(cambioFondo("ninguno", { color: "#123456" }), { estilo: { fondo: null } });
  // sin fondo todavía: uno entero; con fondo: solo la forma (color y opacidad se quedan)
  assert.deepEqual(cambioFondo("pildora", null),
    { estilo: { fondo: { color: "#000000", opacidad: 0.8, radio: 1, relleno_x: 0.03, relleno_y: 0.015 } } });
  assert.deepEqual(cambioFondo("caja", { color: "#123456", opacidad: 0.5, radio: 1 }), { estilo: { fondo: { radio: 0.01 } } });
  assert.throws(() => cambioFondo("nube", null));
  // lo que piden, aplicado de verdad, deja un texto válido con lo pedido
  const d = docBase();
  let r = op.cambiar(d, "t1", cambioFondo("pildora", null), INFO).doc;
  r = op.cambiar(r, "t1", cambioFondo("caja", clipDe(r, "t1").estilo.fondo), INFO).doc;
  r = op.cambiar(r, "t1", cambioContorno(true, r.formato), INFO).doc;
  r = op.cambiar(r, "t1", cambioGrosor(10, r.formato), INFO).doc;
  const m = modelo(r, "t1");
  assert.deepEqual(m.fondo, { tipo: "caja", color: "#000000", opacidad: 80 });
  assert.deepEqual(m.contorno, { activo: true, color: "#000000", grosorPx: 10, min: 1, max: 20 });
});

test("imagen: el % del ancho se vuelve escala (con los topes de cambiar) y «llenar» cubre centrado", () => {
  const clip = { ancho_px: 600, alto_px: 400, transform: { escala: 1 } };
  assert.equal(escalaDePorcentaje(60, clip, null, "9:16"), 0.6 * 1080 / 600);
  assert.equal(escalaDePorcentaje(1, clip, null, "9:16"), 0.05);
  assert.equal(escalaDePorcentaje(9999, clip, null, "9:16"), 5);
  // sin medidas en el clip: las del material; sin ninguna, el tamaño por defecto de una capa (400×200)
  assert.equal(escalaDePorcentaje(50, {}, { ancho: 1080, alto: 1080 }, "9:16"), 0.5);
  assert.equal(escalaDePorcentaje(50, {}, null, "9:16"), 0.5 * 1080 / 400);
  assert.deepEqual(cambioLlenar(clip, null, "9:16"), { transform: { escala: 1920 / 400, x: 0.5, y: 0.5 } });
  assert.deepEqual(cambioLlenar({ ancho_px: 100, alto_px: 100 }, null, "9:16"), { transform: { escala: 5, x: 0.5, y: 0.5 } });
});

test("silenciar guarda el volumen de antes y volver lo devuelve (o 100 % si no había)", () => {
  assert.deepEqual(alternarSilencio(0.7, null), { volumen: 0, recordar: 0.7 });
  assert.deepEqual(alternarSilencio(0, 0.7), { volumen: 0.7, recordar: null });
  assert.deepEqual(alternarSilencio(0, null), { volumen: 1, recordar: null });
  assert.deepEqual(alternarSilencio(0, 0), { volumen: 1, recordar: null });
});

test("textos de los valores: porcentaje, segundos y velocidad con coma", () => {
  assert.equal(textoPorcentaje(45), "45 %");
  assert.equal(textoPorcentaje(33.4), "33 %");
  assert.equal(textoSegundos(500), "0,5 s");
  assert.equal(textoSegundos(1250), "1,3 s");
  assert.equal(textoSegundos(0), "0 s");
  assert.equal(textoSegundos(2000), "2 s");
  assert.equal(textoVelocidad(0.75), "0,75×");
  assert.equal(textoVelocidad(2), "2×");
  assert.equal(COLORES.length, 4);
});

test("motivoRechazo: el mensaje en llano de una operación que no se puede (para decirlo en el panel)", () => {
  assert.match(motivoRechazo(docBase(), "ponerTransicion", ["v1", "fundido", 500], INFO), /último/);
  assert.match(motivoRechazo(docBase(), "editarTexto", ["t1", "   ", "es"], INFO), /vacío/);
  assert.equal(motivoRechazo(docBase(), "cambiar", ["t1", { transform: { x: 0.5 } }], INFO), null);   // sí se puede
});

// ---- Fixes finales de la capa 4b ----

test("un video de una edición sin sonido de la escena muestra el volumen en 0 («Sin sonido») y se puede subir", () => {
  const d = docBase();
  d.pistas = d.pistas.filter((p) => p.id !== "p_sonido");      // un borrador cuya receta no pidió el sonido
  const m = modelo(d, "v0", { info: INFO });
  assert.equal(m.sonido.disponible, true);
  assert.equal(m.sonido.porcentaje, 0);
  assert.match(m.sonido.motivo, /Sin sonido/);
  // mover el deslizador lo crea: ese clip suena, el otro sigue en 0
  const subido = op.volumenSonido(d, "v0", 0.5, INFO).doc;
  assert.equal(modelo(subido, "v0", { info: INFO }).sonido.porcentaje, 50);
  assert.equal(modelo(subido, "v1", { info: INFO }).sonido.porcentaje, 0);
  // a otra velocidad, o de un material sin sonido, sigue sin poder cambiarse
  const lento = op.cambiarVelocidad(d, "v0", 0.5, INFO).doc;
  assert.equal(modelo(lento, "v0", { info: INFO }).sonido.disponible, false);
  assert.match(modelo(lento, "v0", { info: INFO }).sonido.motivo, /velocidad/);
});

test("mensajeRechazo: con la edición cambiada en otra pestaña lo dice así (no «debajo del video»); si no, el porqué", () => {
  assert.equal(mensajeConflicto(), "La edición cambió en otra pestaña: recarga la página para seguir.");
  // en conflicto la operación en sí se podía: el motivo es el conflicto
  assert.equal(mensajeRechazo(docBase(), "cambiar", ["t1", { transform: { x: 0.5 } }], INFO, { conflicto: true }), mensajeConflicto());
  assert.match(mensajeRechazo(docBase(), "ponerTransicion", ["v1", "fundido", 500], INFO), /último/);
  assert.match(mensajeRechazo(docBase(), "cambiar", ["t1", { transform: { x: 0.5 } }], INFO), /No se pudo hacer ese cambio/);
});

test("Propiedades: una operación rechazada vuelve a pintar el control con el valor real y dice el porqué", async () => {
  const { Propiedades } = await import("../../static/editor/propiedades.js");
  for (const [conflicto, esperado] of [[true, mensajeConflicto()], [false, /último/]]) {
    const dichos = [];
    const falsa = {
      editor: { operar: () => false, operarCon: () => false, doc: () => docBase(), info: () => INFO, enConflicto: () => conflicto },
      mensaje: { classList: { contains: () => false } },
      pintadas: 0,
      pintar() { this.pintadas += 1; },
      _decir: (t, error) => dichos.push([t, error]),
    };
    assert.equal(Propiedades.prototype._operar.call(falsa, "v1:transicion", "ponerTransicion", "v1", "fundido", 500), false);
    assert.equal(falsa.pintadas, 1);
    assert.equal(dichos.length, 1);
    assert.equal(dichos[0][1], true);
    if (typeof esperado === "string") assert.equal(dichos[0][0], esperado);
    else assert.match(dichos[0][0], esperado);
  }
});

// ---- Capa 5a (Task 8): «Suena en» y «Subtítulos de este audio» ----
import { cambioSuenaEn } from "../../static/editor/propiedades_modelo.js";

const NOMBRES_IDIOMA = { es: "Español", en: "English", pt: "Português" };

test("modelo de un audio de voz: «Suena en» con su idioma; la música no lo trae", () => {
  const { doc, musica } = docCompleto();
  // una voz agregada en el editor (D8/D9) con el idioma del destino que se veía
  const conVoz = op.agregarAudio(doc, { id: 3 }, 0, { rol: "voz", idioma: "es" }, INFO);
  const m = modelo(conVoz.doc, conVoz.seleccion, { destino: "es_CO", nombresIdioma: NOMBRES_IDIOMA });
  assert.equal(m.forma, "audio");
  assert.deepEqual(m.suena_en, {
    valor: "es",
    opciones: [{ valor: "es", texto: "Solo en Español" }, { valor: "", texto: "Todos los idiomas" }],
  });
  assert.equal(m.subtitulos, true);
  // viendo otro destino, también se puede pasar a ese idioma
  const enOtro = modelo(conVoz.doc, conVoz.seleccion, { destino: "en_US", nombresIdioma: NOMBRES_IDIOMA });
  assert.deepEqual(enOtro.suena_en.opciones.map((o) => o.valor), ["es", "en", ""]);
  assert.equal(enOtro.suena_en.opciones[1].texto, "Solo en English");
  // sin idioma: suena en todos, y ofrece el del destino que se ve
  const todos = op.agregarAudio(doc, { id: 3 }, 0, { rol: "voz" }, INFO);
  const mt = modelo(todos.doc, todos.seleccion, { destino: "pt_BR", nombresIdioma: NOMBRES_IDIOMA });
  assert.deepEqual(mt.suena_en, {
    valor: "", opciones: [{ valor: "pt", texto: "Solo en Português" }, { valor: "", texto: "Todos los idiomas" }],
  });
  // un idioma sin nombre conocido se escribe con su código
  assert.equal(modelo(todos.doc, todos.seleccion, { destino: "fr_FR" }).suena_en.opciones[0].texto, "Solo en fr");
  // la música (y un efecto) no dicen en qué idioma hablan, pero sí ofrecen sus subtítulos
  const mm = modelo(doc, musica, { destino: "es_CO", nombresIdioma: NOMBRES_IDIOMA });
  assert.equal(mm.suena_en, null);
  assert.equal(mm.subtitulos, true);
  // la voz del guion ya se ajusta sola a cada país (por_destino): no lleva «Suena en»
  const guion = structuredClone(doc);
  guion.pistas.find((p) => p.id === "p_voz").clips[0].por_destino = { es_CO: { material_id: 2, duracion_ms: 3000 } };
  assert.equal(modelo(guion, "a1", { destino: "es_CO", nombresIdioma: NOMBRES_IDIOMA }).suena_en, null);
  // una voz de guion (`bloque`) tampoco, aunque todavía no tenga por_destino: la vía
  // automática se lo pone al sumar un destino, y un `idioma` dejaría fuera la voz
  // pagada del otro país (esVozDeGuion, la misma prueba de la pestaña Subtítulos)
  const conBloque = structuredClone(doc);
  conBloque.pistas.find((p) => p.id === "p_voz").clips[0].bloque = "b1";
  assert.equal(modelo(conBloque, "a1", { destino: "es_CO", nombresIdioma: NOMBRES_IDIOMA }).suena_en, null);
  assert.equal(op.esVozDeGuion(conBloque.pistas.find((p) => p.id === "p_voz").clips[0]), true);
  // una voz sin bloque ni por_destino (agregada a mano) sí lo lleva
  assert.equal(modelo(doc, "a1", { destino: "es_CO", nombresIdioma: NOMBRES_IDIOMA }).suena_en.valor, "");
});

test("cambioSuenaEn: lo que pide «Suena en» a operaciones.cambiar", () => {
  assert.deepEqual(cambioSuenaEn("es"), { idioma: "es" });
  assert.deepEqual(cambioSuenaEn(""), { idioma: null });
  assert.deepEqual(cambioSuenaEn(null), { idioma: null });
  const { doc } = docCompleto();
  const conVoz = op.agregarAudio(doc, { id: 3 }, 0, { rol: "voz", idioma: "es" }, INFO);
  const r = op.cambiar(conVoz.doc, conVoz.seleccion, cambioSuenaEn(""), INFO);
  assert.equal(clipDe(r.doc, conVoz.seleccion).idioma, undefined);
  const r2 = op.cambiar(r.doc, conVoz.seleccion, cambioSuenaEn("en"), INFO);
  assert.equal(clipDe(r2.doc, conVoz.seleccion).idioma, "en");
});

// ---- Capa 5b (Tarea 7): la foto en «Editar» y el bloque «Encuadre» ----
import {
  cambioCentrarEncuadre, cambioModoEncuadre, cambioZoomEncuadre, modeloEncuadre, msDeDuracionFoto, textoDuracionFoto,
} from "../../static/editor/propiedades_modelo.js";

const FOTO = { id: 4, tipo: "imagen", ancho: 600, alto: 400 };
function docConFoto() {
  const r = op.agregarFoto(docBase(), FOTO, { despuesDe: "v0" }, INFO);
  return { doc: r.doc, foto: r.seleccion };
}

test("una foto de la principal tiene su formulario: duración, encuadre, zoom lento, transición y borrar", () => {
  const { doc, foto } = docConFoto();
  assert.equal(formaDe(doc, foto), "foto");
  const m = modelo(doc, foto, { info: INFO });
  assert.equal(m.forma, "foto");
  assert.equal(m.clipId, foto);
  assert.equal(claveForma(m), `foto:${foto}`);
  assert.equal(m.nombre, "Foto");
  assert.equal(m.duracionMs, 3000);
  assert.deepEqual(m.duracion, { min: 100, max: op.FOTO_MAX_MS, paso: 100 });
  assert.equal(m.nota, "Una foto no tiene sonido ni velocidad: cambia cuánto dura.");
  assert.equal("velocidad" in m, false);
  assert.equal("sonido" in m, false);
  assert.equal(m.kenBurns, null);
  assert.equal(m.encuadre.modo, "ajustar");                // 600×400 en 9:16: entra con el fondo desenfocado (D7)
  assert.equal(m.transicion.disponible, true);              // va antes de v1
  assert.equal(m.transicion.tipo, "corte");
  assert.match(m.transicion.ayuda, /Junta los dos clips/);
  assert.deepEqual(m.transiciones.map((x) => x.valor), op.TRANSICIONES);
  assert.equal(m.puedeBorrar, true);
  assert.equal(m.motivoBorrar, null);
  // con zoom lento y otra duración
  const larga = op.cambiarDuracionFoto(op.cambiar(doc, foto, { ken_burns: "out" }, INFO).doc, foto, 4500, INFO).doc;
  const m2 = modelo(larga, foto, { info: INFO });
  assert.equal(m2.duracionMs, 4500);
  assert.equal(m2.kenBurns, "out");
  // la última foto no tiene transición hacia el siguiente
  const ultima = op.agregarFoto(docBase(), FOTO, { despuesDe: "v1" }, INFO);
  const m3 = modelo(ultima.doc, ultima.seleccion, { info: INFO });
  assert.equal(m3.transicion.disponible, false);
  assert.equal(m3.transicion.ayuda, null);
});

test("el video también trae su encuadre (por defecto: llenar, sin acercar, centrado)", () => {
  const d = docBase();
  const m = modelo(d, "v0", { info: INFO });
  assert.equal(m.encuadre.modo, "llenar");
  assert.equal(m.encuadre.zoomPct, 100);
  assert.equal(m.encuadre.centrado, true);
  assert.equal(m.encuadre.sinMargen, false);               // sin medidas no se sabe: no lo dice
  assert.deepEqual(m.encuadre.opciones, [
    { valor: "llenar", texto: "Llenar" }, { valor: "ajustar", texto: "Ajustar con fondo desenfocado" }]);
  const ajustado = op.cambiar(d, "v0", { encuadre: { modo: "ajustar", zoom: 1.5 } }, INFO).doc;
  const e = modelo(ajustado, "v0", { info: INFO }).encuadre;
  assert.deepEqual([e.modo, e.zoomPct, e.centrado], ["ajustar", 150, true]);
  const corrido = op.cambiar(d, "v0", { encuadre: { x: 0.3 } }, INFO).doc;
  assert.equal(modelo(corrido, "v0", { info: INFO }).encuadre.centrado, false);
});

test("modeloEncuadre: sin margen solo si el cuadro mide justo el lienzo (llenar, sin acercar, misma proporción)", () => {
  const clip = { encuadre: null };
  assert.equal(modeloEncuadre(clip, { medidas: [1080, 1920], formato: "9:16" }).sinMargen, true);
  assert.equal(modeloEncuadre(clip, { medidas: [540, 960], formato: "9:16" }).sinMargen, true);
  assert.equal(modeloEncuadre(clip, { medidas: [400, 200], formato: "9:16" }).sinMargen, false);
  assert.equal(modeloEncuadre({ encuadre: { zoom: 1.5 } }, { medidas: [1080, 1920], formato: "9:16" }).sinMargen, false);
  assert.equal(modeloEncuadre(clip).sinMargen, false);
  assert.deepEqual(modeloEncuadre({ encuadre: { modo: "ajustar", zoom: 2.25 } }).zoomPct, 225);
  // el modelo del panel toma las medidas de quien dibuja; si no, las del material
  const d = docBase();
  assert.equal(modelo(d, "v0", { info: INFO, medidasPrincipal: () => [1080, 1920] }).encuadre.sinMargen, true);
  assert.equal(modelo(d, "v0", { info: INFO, materiales: { 1: { ancho: 1080, alto: 1920 } } }).encuadre.sinMargen, true);
  assert.equal(modelo(d, "v0", { info: INFO, materiales: { 1: { ancho: 1920, alto: 1080 } } }).encuadre.sinMargen, false);
});

// Revisión final de la capa 5b: un margen más chico que el imán cuenta como
// «sin margen» (igual que encuadre.sinMargen), y la ayuda habla de «la
// imagen» (sirve para un video y para una foto).
test("modeloEncuadre: un margen menor que el imán (1080×1918) es «sin margen», y los textos hablan de la imagen", () => {
  const m = modeloEncuadre({ encuadre: null }, { medidas: [1080, 1918], formato: "9:16" });
  assert.equal(m.sinMargen, true);
  assert.equal(m.aviso, "Acerca la imagen para poder moverla.");
  assert.equal(m.ayuda, "Arrastra la imagen para elegir qué parte se ve; la esquina la acerca.");
  assert.equal(modeloEncuadre({ encuadre: { modo: "ajustar" } }, { medidas: [1080, 1918], formato: "9:16" }).sinMargen, true);
  assert.equal(modeloEncuadre({ encuadre: null }, { medidas: [1110, 1920], formato: "9:16" }).sinMargen, false);
});

test("los cambios del bloque «Encuadre» son los que acepta operaciones.cambiar", () => {
  assert.deepEqual(cambioModoEncuadre("ajustar"), { encuadre: { modo: "ajustar" } });
  assert.deepEqual(cambioZoomEncuadre(150), { encuadre: { zoom: 1.5 } });
  assert.deepEqual(cambioCentrarEncuadre(), { encuadre: { x: 0.5, y: 0.5 } });
  let d = docBase();
  for (const c of [cambioModoEncuadre("ajustar"), cambioZoomEncuadre(150), { encuadre: { x: 0.2 } }, cambioCentrarEncuadre()]) {
    d = op.cambiar(d, "v0", c, INFO).doc;
  }
  assert.deepEqual(clipDe(d, "v0").encuadre, { modo: "ajustar", zoom: 1.5, x: 0.5, y: 0.5 });
  // de vuelta a llenar y sin acercar: sin encuadre (el de siempre)
  d = op.cambiar(op.cambiar(d, "v0", cambioModoEncuadre("llenar"), INFO).doc, "v0", cambioZoomEncuadre(100), INFO).doc;
  assert.equal(clipDe(d, "v0").encuadre, null);
});

test("la transición dice que junta los dos clips cuando no hay una o es «solape»; una de cola no", () => {
  const d = docBase();
  assert.match(modelo(d, "v0", { info: INFO }).transicion.ayuda, /queda tan corto/);
  const solape = op.ponerTransicion(d, "v0", "fundido", 500, INFO).doc;
  assert.equal(clipDe(solape, "v0").transicion.modo, "solape");
  assert.match(modelo(solape, "v0", { info: INFO }).transicion.ayuda, /queda tan corto/);
  const cola = docBase();
  clipDe(cola, "v0").transicion = { tipo: "fundido", duracion_ms: 500 };   // la de un borrador automático
  assert.equal(modelo(cola, "v0", { info: INFO }).transicion.ayuda, null);
  assert.equal(modelo(d, "v1", { info: INFO }).transicion.ayuda, null);     // el último: no hay transición
});

test("la duración de la foto se escribe en segundos con la coma y se lee con coma o punto", () => {
  assert.equal(textoDuracionFoto(3000), "3");
  assert.equal(textoDuracionFoto(2500), "2,5");
  assert.equal(textoDuracionFoto(100), "0,1");
  assert.equal(textoDuracionFoto(60000), "60");
  assert.equal(msDeDuracionFoto("2,5"), 2500);
  assert.equal(msDeDuracionFoto("2.5"), 2500);
  assert.equal(msDeDuracionFoto(" 3 s "), 3000);
  assert.equal(msDeDuracionFoto("0,1"), 100);
  assert.equal(msDeDuracionFoto("1,26"), 1300);            // de a 100 ms
  assert.equal(msDeDuracionFoto(""), null);
  assert.equal(msDeDuracionFoto("tres"), null);
  assert.equal(msDeDuracionFoto("-2"), null);
});

// ---- Capa 5c (Tarea 7): ancho del texto, fuentes por familia, avisos de lo que no sale y el color de un sticker ----
import { readFileSync } from "node:fs";
import {
  avisosTexto, CATEGORIAS_FUENTE, cambioAncho, cambioSinLimite,
} from "../../static/editor/propiedades_modelo.js";

const TABLA = JSON.parse(readFileSync(new URL("../../static/editor/tipografia.json", import.meta.url), "utf8"));
const T0 = { ...TABLA, emoji: null };
const T_E = { ...T0, emoji: { id: "E", upem: 1000, asc: 900, desc: 200,
  avances: [[0x2764, [1000]], [0x1F44D, [1000]], [0x1F468, [1000]], [0x1F525, [1000]]] } };
// Un catálogo de 4 (dos clásicas, una de impacto, una con serifa), desordenado a propósito.
const CATALOGO_4 = [
  { id: "Inter-Bold", nombre: "Inter Bold", categoria: "clasicas" },
  { id: "DMSerifDisplay-Regular", nombre: "DM Serif Display", categoria: "serifa" },
  { id: "Anton-Regular", nombre: "Anton", categoria: "impacto" },
  { id: "SpaceGrotesk-Bold", nombre: "Space Grotesk", categoria: "clasicas" },
];
const STICKER = { id: 9, tipo: "imagen", ancho: 512, alto: 512, tenible: true };
const v2 = (fuente) => ({ estilo: { fuente, version: 2 } });
const v1 = (fuente) => ({ estilo: { fuente } });

test("modelo de un texto: «Ancho del texto» en % y «Sin límite» (D7.2)", () => {
  const titulo = op.agregarTexto(docBase(), 0, "titulo", {}, INFO);
  assert.deepEqual(modelo(titulo.doc, titulo.seleccion).ancho, { pct: 86, sinLimite: false, min: 30, max: 100 });
  const precio = op.agregarTexto(docBase(), 0, "precio", {}, INFO);
  assert.deepEqual(modelo(precio.doc, precio.seleccion).ancho, { pct: 86, sinLimite: true, min: 30, max: 100 });
  const llamado = op.agregarTexto(docBase(), 0, "llamado", {}, INFO);
  assert.equal(modelo(llamado.doc, llamado.seleccion).ancho.pct, 80);
  // un texto de antes sin ancho (el de docBase) no tiene límite; el del borrador (0,8889) se ve redondeado
  assert.deepEqual(modelo(docBase(), "t1").ancho, { pct: 86, sinLimite: true, min: 30, max: 100 });
  const borrador = docBase();
  clipDe(borrador, "t1").estilo.ancho_max = 0.8889;
  assert.deepEqual(modelo(borrador, "t1").ancho, { pct: 89, sinLimite: false, min: 30, max: 100 });
  clipDe(borrador, "t1").estilo.ancho_max = 0.1;                 // más angosto de lo que ofrece el deslizador
  assert.equal(modelo(borrador, "t1").ancho.pct, 30);
  // v2: si el texto ya es nuevo
  assert.equal(modelo(titulo.doc, titulo.seleccion).v2, true);
  assert.equal(modelo(docBase(), "t1").v2, false);
});

test("cambioAncho y cambioSinLimite: el % del deslizador acotado a 30–100, «Sin límite» es null", () => {
  assert.deepEqual(cambioAncho(50), { estilo: { ancho_max: 0.5 } });
  assert.deepEqual(cambioAncho(120), { estilo: { ancho_max: 1 } });
  assert.deepEqual(cambioAncho(5), { estilo: { ancho_max: 0.3 } });
  assert.deepEqual(cambioAncho(86), { estilo: { ancho_max: 0.86 } });
  assert.deepEqual(cambioSinLimite(true), { estilo: { ancho_max: null } });
  assert.deepEqual(cambioSinLimite(false), { estilo: { ancho_max: op.ANCHO_TEXTO.defecto } });
  // y operaciones.cambiar los aplica (y pasa el texto a v2)
  const d = op.cambiar(docBase(), "t1", cambioAncho(50), INFO).doc;
  assert.deepEqual([clipDe(d, "t1").estilo.ancho_max, clipDe(d, "t1").estilo.version], [0.5, 2]);
});

test("modelo de un texto: las fuentes agrupadas por familia, en el orden de las familias y solo las que tienen fuentes (D9.4)", () => {
  assert.deepEqual(CATEGORIAS_FUENTE, ["clasicas", "impacto", "redondeadas", "manuscritas", "serifa"]);
  const titulo = op.agregarTexto(docBase(), 0, "titulo", {}, INFO);
  const m = modelo(titulo.doc, titulo.seleccion, { catalogoFuentes: CATALOGO_4, tabla: T0 });
  assert.deepEqual(m.fuentes, [
    { categoria: "clasicas", texto: "Clásicas",
      fuentes: [{ valor: "Inter-Bold", texto: "Inter Bold" }, { valor: "SpaceGrotesk-Bold", texto: "Space Grotesk" }] },
    { categoria: "impacto", texto: "De impacto", fuentes: [{ valor: "Anton-Regular", texto: "Anton" }] },
    { categoria: "serifa", texto: "Con serifa", fuentes: [{ valor: "DMSerifDisplay-Regular", texto: "DM Serif Display" }] },
  ]);
  // el catálogo entero (el de la página): cinco familias con sus nombres, ninguna vacía
  const todas = op.FUENTES.map((id) => ({ id, nombre: id, categoria: null }));
  const reales = [["clasicas", 4], ["impacto", 3], ["redondeadas", 1], ["manuscritas", 2], ["serifa", 1]];
  let i = 0;
  for (const [cat, n] of reales) for (let k = 0; k < n; k++) todas[i++].categoria = cat;
  const completo = modelo(titulo.doc, titulo.seleccion, { catalogoFuentes: todas });
  assert.deepEqual(completo.fuentes.map((g) => [g.categoria, g.texto, g.fuentes.length]), [
    ["clasicas", "Clásicas", 4], ["impacto", "De impacto", 3], ["redondeadas", "Redondeadas", 1],
    ["manuscritas", "Manuscritas", 2], ["serifa", "Con serifa", 1]]);
  // una categoría que no se conoce no se ofrece (no sale un grupo sin nombre)
  const rara = modelo(titulo.doc, titulo.seleccion, { catalogoFuentes: [...CATALOGO_4, { id: "X-Bold", nombre: "X", categoria: "rara" }] });
  assert.equal(rara.fuentes.length, 3);
});

test("avisosTexto: lo que no sale en el video (v2), lo simplificado y el texto de antes con emojis (v1)", () => {
  assert.deepEqual(avisosTexto(v2("SpaceGrotesk-Bold"), "✓ Envío", T0),
    [{ texto: "No sale en el video: «✓» (esta fuente no los tiene).", accion: null }]);
  assert.deepEqual(avisosTexto(v2("Inter-Bold"), "👍🏽 listo", T_E),
    [{ texto: "Las banderas, los tonos de piel y los emojis compuestos salen simplificados.", accion: null }]);
  assert.deepEqual(avisosTexto(v1("Inter-Bold"), "Hola 🔥", T0),
    [{ texto: "Este texto es de antes: sus emojis no salen en el video.", accion: "actualizar" }]);
  assert.deepEqual(avisosTexto(v1("Inter-Bold"), "Hola, ¿qué tal? Ñandú", T0), []);
  assert.deepEqual(avisosTexto(v2("Inter-Bold"), "Hola 🔥", T_E), [], "con la fuente de emojis, el 🔥 sale");
  // varios que faltan: unidos sin separador, cada uno una vez y en el orden en que aparecen
  assert.deepEqual(avisosTexto(v2("Inter-Bold"), "🔥 hola 🍕 🔥", T0),
    [{ texto: "No sale en el video: «🔥🍕» (esta fuente no los tiene).", accion: null }]);
  // los dos avisos juntos: lo que falta primero
  assert.deepEqual(avisosTexto(v2("Inter-Bold"), "👍🏽 🍕", T_E).map((a) => a.texto), [
    "No sale en el video: «🍕» (esta fuente no los tiene).",
    "Las banderas, los tonos de piel y los emojis compuestos salen simplificados."]);
  // sin tabla, o con una fuente que la tabla no trae: nada (y no lanza)
  assert.deepEqual(avisosTexto(v2("Inter-Bold"), "Hola 🔥", null), []);
  assert.deepEqual(avisosTexto(v2("Inexistente-Bold"), "Hola 🔥", T0), []);
  assert.deepEqual(avisosTexto({}, "Hola 🔥", T0), []);
});

test("modelo de un texto: los avisos van con el texto que se ve, y el de antes ofrece «Mostrar los emojis»", () => {
  const conEmoji = op.editarTexto(docBase(), "t1", "Hola 🔥", "es", INFO).doc;      // al escribir, pasa a v2
  assert.deepEqual(modelo(conEmoji, "t1", { tabla: T0 }).avisos,
    [{ texto: "No sale en el video: «🔥» (esta fuente no los tiene).", accion: null }]);
  assert.deepEqual(modelo(conEmoji, "t1", { tabla: T_E }).avisos, []);
  const viejo = docBase();
  clipDe(viejo, "t1").texto = { literal: "Hola 🔥" };                               // un borrador de antes
  assert.deepEqual(modelo(viejo, "t1", { tabla: T_E }).avisos,
    [{ texto: "Este texto es de antes: sus emojis no salen en el video.", accion: "actualizar" }]);
  assert.deepEqual(modelo(viejo, "t1").avisos, [], "sin la tabla, nada que decir");
  const actualizado = op.actualizarTexto(viejo, "t1", INFO).doc;
  assert.deepEqual(modelo(actualizado, "t1", { tabla: T_E }).avisos, []);
});

test("modelo de una imagen: el color solo si su material se tiñe (un sticker)", () => {
  const r = op.agregarImagen(docBase(), STICKER, 0, { fraccion: 0.35, tinte: "#FFD400" }, INFO);
  const m = modelo(r.doc, r.seleccion, { materiales: { 9: STICKER } });
  assert.equal(m.tinte.activo, true);
  assert.equal(m.tinte.color, "#FFD400");
  assert.deepEqual(m.tinte.paleta.map((c) => c.color), ["#FFFFFF", "#000000", "#7C3AED", "#FFD60A", "#E53935"]);
  assert.deepEqual(m.tinte.paleta.filter((c) => c.elegido), []);
  const blanco = op.cambiar(r.doc, r.seleccion, { tinte: "#FFFFFF" }, INFO).doc;
  assert.deepEqual(modelo(blanco, r.seleccion, { materiales: { 9: STICKER } }).tinte.paleta.filter((c) => c.elegido).map((c) => c.nombre),
    ["Blanco"]);
  // sin tinte: el sticker se ve blanco (su PNG es blanco)
  const sin = op.cambiar(r.doc, r.seleccion, { tinte: null }, INFO).doc;
  assert.deepEqual([modelo(sin, r.seleccion, { materiales: { 9: STICKER } }).tinte.activo,
    modelo(sin, r.seleccion, { materiales: { 9: STICKER } }).tinte.color], [false, "#FFFFFF"]);
  // una foto (no se tiñe) o un material que no se conoce: sin color
  const { doc, imagen } = docCompleto();
  assert.equal(modelo(doc, imagen, { materiales: { 4: IMAGEN } }).tinte, null);
  assert.equal(modelo(r.doc, r.seleccion).tinte, null);
});
