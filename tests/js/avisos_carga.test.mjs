// Capa 4c (4/10): los avisos de carga se recalculan tras cada cambio y
// hablan en llano (sin ids ni milisegundos).
import { test } from "node:test";
import assert from "node:assert/strict";
import { avisosCarga, faltantes, materialesUsados, TEXTO_PIDE_DE_MAS, TEXTO_SE_ACORTO } from "../../static/editor/avisos_carga.js";
import * as op from "../../static/editor/operaciones.js";
import { docBase, DURACIONES } from "./doc_base.mjs";

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
  assert.deepEqual(antes.recortes, { texto: TEXTO_PIDE_DE_MAS, error: true });
  assert.doesNotMatch(antes.recortes.texto, tecnico);
  // cualquier operación termina en normalizar: con el documento ya arreglado el aviso se va
  const arreglado = op.moverA(doc, "t1", 2000, info).doc;
  assert.deepEqual(op.clipsQuePidenDeMas(arreglado, info), []);
  assert.equal(avisosCarga(arreglado, info, MATS).recortes, null);
  // la página lo acortó al abrir: se dice una vez, sin rojo
  assert.deepEqual(avisosCarga(arreglado, info, MATS, { acortado: true }).recortes, { texto: TEXTO_SE_ACORTO, error: false });
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
