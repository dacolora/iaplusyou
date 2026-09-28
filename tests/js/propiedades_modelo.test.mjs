// El panel de propiedades (capa 4b, Task 7): lo puro de propiedades_modelo.js
// — qué formulario toca a lo elegido, los valores que muestra y los cambios
// que pide. La clase `Propiedades` (propiedades.js) es DOM y no corre en Node;
// importarla sí (modulos_navegador.test.mjs).
import { test } from "node:test";
import assert from "node:assert/strict";
import * as op from "../../static/editor/operaciones.js";
import {
  alternarSilencio, AYUDA_VACIA, cambioContorno, cambioFondo, cambioGrosor, cambioLlenar, cambioSombra, claveForma,
  COLORES, escalaDePorcentaje, formaDe, modelo, motivoRechazo, textoPorcentaje, textoSegundos, textoVelocidad,
  TRANSICION_MS,
} from "../../static/editor/propiedades_modelo.js";
import { docBase } from "./doc_base.mjs";

const INFO = { 1: { duracion_ms: 8000, tiene_audio: true }, 2: { duracion_ms: 3000 }, 3: { duracion_ms: 1500, tiene_audio: false } };
const IMAGEN = { id: 4, tipo: "imagen", ancho: 600, alto: 400 };
const clipDe = (d, id) => d.pistas.flatMap((p) => p.clips).find((c) => c.id === id);

// docBase + una imagen, una música y un texto «Título»; devuelve el doc y los ids nuevos.
function docCompleto() {
  const conImagen = op.agregarImagen(docBase(), IMAGEN, 0, {}, INFO);
  const conMusica = op.agregarAudio(conImagen.doc, { id: 2 }, 0, { rol: "musica" }, INFO);
  const conTexto = op.agregarTexto(conMusica.doc, 4000, "titulo", INFO);
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
  assert.equal(m.ayuda, AYUDA_VACIA);
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
    min: 200, max: 1500, paso: 100 });
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
  assert.deepEqual(m.fuentes.map((f) => f.valor), ["Inter-Bold", "Inter-SemiBold", "SpaceGrotesk-Bold"]);
  assert.ok(m.fuentes.every((f) => f.texto));
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
  const precio = op.agregarTexto(docBase(), 0, "precio", INFO);
  assert.deepEqual(modelo(precio.doc, precio.seleccion).fondo, { tipo: "pildora", color: "#7C3AED", opacidad: 100 });
  const llamado = op.agregarTexto(docBase(), 0, "llamado", INFO);
  assert.deepEqual(modelo(llamado.doc, llamado.seleccion).fondo, { tipo: "caja", color: "#FFFFFF", opacidad: 90 });
  assert.equal(modelo(llamado.doc, llamado.seleccion).paleta.find((c) => c.elegido).nombre, "Negro");
  const sub = op.agregarTexto(docBase(), 0, "subtitulo", INFO);
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
