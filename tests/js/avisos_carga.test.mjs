// Capa 4c (4/10): los avisos de carga se recalculan tras cada cambio y
// hablan en llano (sin ids ni milisegundos).
import { test } from "node:test";
import assert from "node:assert/strict";
import { avisosCarga, faltantes, materialesUsados, textoPideDeMas, textoSeAcorto } from "../../static/editor/avisos_carga.js";
import * as op from "../../static/editor/operaciones.js";
import { docBase, docConVozYPalabras, DURACIONES, INFO_PALABRAS } from "./doc_base.mjs";

const MATS = { 1: { id: 1 }, 2: { id: 2 } };
const tecnico = /\bv\d|\bs\d|\bms\b|\d{3,}|'/;

// v1 pide 4000–8000 de un clon que (ahora se sabe) mide 7000 ms.
function pideDeMas() {
  return { doc: docBase(), info: { ...DURACIONES, 1: 7000 } };
}

test("un clip que pide más material del que hay se avisa en llano, y se va en cuanto normalizar lo arregla", () => {
  const { doc, info } = pideDeMas();
  assert.deepEqual(op.clipsQuePidenDeMas(doc, info), ["v1"]);
  const antes = avisosCarga(doc, info, MATS);
  assert.deepEqual(antes.recortes, { texto: textoPideDeMas(), error: true });
  assert.doesNotMatch(antes.recortes.texto, tecnico);
  // cualquier operación termina en normalizar: con el documento ya arreglado el aviso se va
  const arreglado = op.moverA(doc, "t1", 2000, info).doc;
  assert.deepEqual(op.clipsQuePidenDeMas(arreglado, info), []);
  assert.equal(avisosCarga(arreglado, info, MATS).recortes, null);
  // la página lo acortó al abrir: se dice una vez, sin rojo
  assert.deepEqual(avisosCarga(arreglado, info, MATS, { acortado: true }).recortes, { texto: textoSeAcorto(), error: false });
});

test("la música (en bucle) y un material sin duración conocida no cuentan como pedir de más", () => {
  const doc = docBase();
  doc.pistas[2].clips[0].rol_audio = "musica";
  assert.deepEqual(op.clipsQuePidenDeMas(doc, { 1: 8000, 2: 1000 }), []);
  assert.deepEqual(op.clipsQuePidenDeMas(docBase(), { 1: null, 2: { duracion_ms: null } }), []);
});

test("los archivos que faltan se cuentan de lo que la edición usa de verdad, y el aviso se va al quitarlo", () => {
  const doc = docBase();
  doc.materiales = [1, 2, 99];                          // 99: quedó en la lista vieja, ningún clip lo usa
  doc.pngs = { t1: 20 };
  doc.marca.logo_material_id = 30;
  doc.pistas[2].clips[0].por_destino = { en_US: { material_id: 40, duracion_ms: 3000 } };
  assert.deepEqual([...materialesUsados(doc)].sort((a, b) => a - b), [1, 2, 20, 30, 40]);
  assert.deepEqual(faltantes(doc, { ...MATS, 20: {}, 30: {} }), [40]);
  const uno = avisosCarga(doc, DURACIONES, { ...MATS, 20: {}, 30: {} });
  assert.equal(uno.faltan.texto, "Falta 1 archivo de esta edición (se borró o no es de este proyecto): esa parte no se verá.");
  assert.doesNotMatch(uno.faltan.texto, tecnico);
  const dos = avisosCarga(doc, DURACIONES, MATS);
  assert.match(dos.faltan.texto, /^Faltan 3 archivos de esta edición/);
  // borrar la voz que usaba el archivo 40 (y dejar lo demás) quita ese faltante
  const sinVoz = op.borrar(doc, "a1", DURACIONES).doc;
  assert.equal(avisosCarga(sinVoz, DURACIONES, { ...MATS, 20: {}, 30: {} }).faltan, null);
});

// ---- Arreglo 1 (crítico) y borde del ítem 4: lo que la página arregla al abrir ----
import { arreglarAlAbrir, textoNoCabe } from "../../static/editor/avisos_carga.js";

test("arreglarAlAbrir acorta lo que se puede y, ya arreglado, no pide guardar otra vez", () => {
  const { doc, info } = pideDeMas();
  const r = arreglarAlAbrir(doc, info);
  assert.equal(r.guardar, true);
  assert.equal(r.acortado, true);
  assert.deepEqual(op.clipsQuePidenDeMas(r.doc, info), []);
  const otraVez = arreglarAlAbrir(r.doc, info);
  assert.deepEqual([otraVez.guardar, otraVez.acortado], [false, false]);
  assert.equal(otraVez.doc, r.doc, "sin cambios: el mismo documento, nada que guardar");
  const sano = docBase();
  assert.deepEqual(arreglarAlAbrir(sano, DURACIONES), { doc: sano, guardar: false, acortado: false });
});

test("un archivo más corto que el mínimo de un clip: no se promete «se acorta solo» ni se guarda en cada carga", () => {
  const info = { ...DURACIONES, 2: 60 };                   // la voz a1 pide 3000 ms de un audio de 60 ms
  const doc = docBase();
  const primera = arreglarAlAbrir(doc, info);
  assert.deepEqual(op.clipsQuePidenDeMas(primera.doc, info), ["a1"], "ni acortándola al mínimo cabe");
  const segunda = arreglarAlAbrir(primera.doc, info);
  assert.equal(segunda.guardar, false, "la segunda carga ya no cambia nada: no se guarda");
  for (const d of [doc, primera.doc]) {
    const a = avisosCarga(d, info, MATS, { acortado: primera.acortado });
    assert.deepEqual(a.recortes, { texto: textoNoCabe(), error: true });
    assert.doesNotMatch(a.recortes.texto, /próximo cambio|se acortó/);
    assert.doesNotMatch(a.recortes.texto, tecnico);
  }
});

test("arreglarAlAbrir le pone su duración a un «deslizar» guardado sin ella (ediciones de la capa 4b), sin decir «se acortó»", () => {
  const doc = docBase();
  doc.pistas[1].clips[0].animacion = { entrada: "deslizar" };
  const r = arreglarAlAbrir(doc, DURACIONES);
  assert.deepEqual([r.guardar, r.acortado], [true, false]);
  assert.deepEqual(r.doc.pistas[1].clips[0].animacion, { entrada: "deslizar", duracion_ms: op.DURACION_ANIMACION_MS });
  assert.equal(avisosCarga(r.doc, DURACIONES, MATS, { acortado: r.acortado }).recortes, null);
});

// ---- Capa 5a (Tarea 4, D14): la voz se adopta como fuente al abrir ----
test("arreglarAlAbrir adopta la voz como fuente de subtítulos de un borrador automático, y pide guardar", () => {
  const doc = docConVozYPalabras();
  const r = arreglarAlAbrir(doc, INFO_PALABRAS);
  assert.equal(r.guardar, true);
  assert.equal(r.acortado, false, "no hubo que acortar nada: solo adoptó");
  assert.deepEqual(r.doc.subtitulos.fuentes, { es: [{ tipo: "voz" }] });
  assert.equal(doc.subtitulos.fuentes, undefined, "no toca el documento de entrada");
  const otraVez = arreglarAlAbrir(r.doc, INFO_PALABRAS);
  assert.equal(otraVez.guardar, false, "ya adoptado: la segunda vuelta no pide guardar de nuevo");
});
