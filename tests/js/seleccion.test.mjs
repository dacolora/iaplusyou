import test from "node:test";
import assert from "node:assert/strict";
import { cajaCapa, capaEnPunto, moverCapa, escalarCapa } from "../../static/editor/seleccion.js";
import { posicionCapa } from "../../static/editor/tiempo.js";
import { docBase } from "./doc_base.mjs";

test("la caja usa la misma posición animada que el reproductor", () => {
  const doc = docBase(), c = doc.pistas[1].clips[0];
  c.animacion = { entrada: "deslizar", duracion_ms: 500 };
  const p = posicionCapa(c, 1100, 600, 120, doc.formato);
  assert.deepEqual(cajaCapa(doc, c, 1100, {}, { t1: [600, 120] }),
    { x: p.x, y: p.y, ancho: p.w, alto: p.h });
});

test("elige la última capa visible y respeta tiempo y tamaño del material", () => {
  const doc = docBase();
  const c = { ...structuredClone(doc.pistas[1].clips[0]), id: "foto", material_id: 3 };
  delete c.texto;
  doc.pistas.push({ id: "p_imagen", tipo: "imagen", clips: [c] });
  const mats = { 3: { ancho: 800, alto: 400 } };
  assert.deepEqual(cajaCapa(doc, c, 1500, mats, {}), { x: 140, y: 760, ancho: 800, alto: 400 });
  assert.equal(capaEnPunto(doc, 1500, 540, 960, mats, {}), "foto");
  doc.pistas.at(-1).oculta = true;
  assert.equal(capaEnPunto(doc, 1500, 540, 960, mats, {}), "t1");
  assert.equal(capaEnPunto(doc, 3000, 540, 960, mats, {}), null);
  assert.equal(capaEnPunto(doc, 1500, 0, 0, mats, {}), null);
});

test("mover limita al lienzo y muestra las guías del centro", () => {
  assert.deepEqual(moverCapa({ x: 0.49, y: 0.5 }, 0, 2, "9:16"),
    { x: 0.5, y: 0.5, guias: { vertical: true, horizontal: true } });
  assert.deepEqual(moverCapa({ x: 0.1, y: 0.9 }, -1000, 1000, "9:16"),
    { x: 0, y: 1, guias: { vertical: false, horizontal: false } });
});

test("escalar conserva proporciones y limita los extremos", () => {
  const b = { x: 0, y: 0, ancho: 200, alto: 100 };
  assert.equal(escalarCapa({ escala: 1 }, b, 100, 50), 2);
  assert.equal(escalarCapa({ escala: 1 }, b, -100, -50), 0.05);
  assert.equal(escalarCapa({ escala: 1 }, b, 10000, 5000), 5);
  assert.equal(escalarCapa({ escala: 2 }, { ancho: 0, alto: 0 }, 0, 0), 2);
});

// ---- Task 8: lo que necesita la capa para tocar sobre el video ----
import {
  asaDe, cajaElegida, cambiosArrastre, cursorEn, esDobleToque, escalarDesdeAsa, esTexto, gestoEn, porcentaje,
  puntoEnLienzo, superaUmbral,
} from "../../static/editor/seleccion.js";

// t1 (texto, 1000..3000, centrado) medido 600×120 y encima una foto 800×400.
function conFoto() {
  const doc = docBase();
  const foto = { ...structuredClone(doc.pistas[1].clips[0]), id: "foto", material_id: 3 };
  delete foto.texto;
  doc.pistas.push({ id: "p_imagen", tipo: "imagen", clips: [foto] });
  return doc;
}
const MATS = { 3: { ancho: 800, alto: 400 } };
const MEDIDAS = { t1: [600, 120] };

test("el punto del puntero pasa a píxeles del lienzo con la proporción mostrada", () => {
  const rect = { left: 10, top: 20, width: 270, height: 480 };
  assert.deepEqual(puntoEnLienzo(145, 260, rect, 1080, 1920), { x: 540, y: 960 });
  assert.deepEqual(puntoEnLienzo(10, 20, rect, 1080, 1920), { x: 0, y: 0 });
  assert.equal(puntoEnLienzo(145, 260, { left: 0, top: 0, width: 0, height: 0 }, 1080, 1920), null);   // oculto
});

test("la caja de lo elegido solo existe si es una capa activa en ese instante", () => {
  const doc = conFoto();
  assert.deepEqual(cajaElegida(doc, 1500, "t1", MATS, MEDIDAS), { x: 240, y: 900, ancho: 600, alto: 120, ancla: "centro" });
  assert.deepEqual(cajaElegida(doc, 1500, "foto", MATS, {}), { x: 140, y: 760, ancho: 800, alto: 400, ancla: "centro" });
  assert.equal(cajaElegida(doc, 3000, "t1", MATS, MEDIDAS), null);      // ya terminó
  assert.equal(cajaElegida(doc, 1500, "v0", MATS, MEDIDAS), null);      // el video principal no es una capa
  assert.equal(cajaElegida(doc, 1500, "a1", MATS, MEDIDAS), null);      // el audio tampoco
  assert.equal(cajaElegida(doc, 1500, null, MATS, MEDIDAS), null);
  assert.equal(cajaElegida(null, 1500, "t1", MATS, MEDIDAS), null);
  doc.pistas[1].oculta = true;
  assert.equal(cajaElegida(doc, 1500, "t1", MATS, MEDIDAS), null);      // pista oculta: no se ve
});

test("el asa va en la esquina opuesta al ancla y nunca se sale del lienzo", () => {
  const b = { x: 240, y: 900, ancho: 600, alto: 120 };
  assert.deepEqual(asaDe(b), { x: 840, y: 1020, sx: 1, sy: 1 });
  assert.deepEqual(asaDe(b, "centro"), { x: 840, y: 1020, sx: 1, sy: 1 });
  assert.deepEqual(asaDe(b, "sup_izq"), { x: 840, y: 1020, sx: 1, sy: 1 });
  assert.deepEqual(asaDe(b, "sup_der"), { x: 240, y: 1020, sx: -1, sy: 1 });
  assert.deepEqual(asaDe(b, "inf_izq"), { x: 840, y: 900, sx: 1, sy: -1 });
  assert.deepEqual(asaDe(b, "inf_der"), { x: 240, y: 900, sx: -1, sy: -1 });
  // una foto que llena la pantalla (más grande que el lienzo): el asa queda adentro, a la vista
  const grande = { x: -100, y: -100, ancho: 1400, alto: 2200 };
  assert.deepEqual(asaDe(grande, "centro", "9:16", 20), { x: 1060, y: 1900, sx: 1, sy: 1 });
  assert.deepEqual(asaDe(b, "centro", "9:16", 20), { x: 840, y: 1020, sx: 1, sy: 1 });
});

test("agrandar desde el asa sigue al dedo con cualquier ancla y no se da vuelta al pasar el centro", () => {
  const b = { x: 0, y: 0, ancho: 200, alto: 100 };
  assert.equal(escalarDesdeAsa({ escala: 1, ancla: "centro" }, b, 100, 50), 2);
  assert.equal(escalarDesdeAsa({ escala: 1 }, b, 100, 50), 2);                        // sin ancla = centro
  // más allá del centro la distancia vuelve a crecer: sin tope daría 2 (se daría vuelta)
  assert.equal(escalarCapa({ escala: 1 }, b, -300, -150), 2);
  assert.equal(escalarDesdeAsa({ escala: 1 }, b, -300, -150), 0.05);
  // ancla arriba a la derecha: el asa es la de abajo a la izquierda y la caja crece desde el ancla
  assert.equal(escalarDesdeAsa({ escala: 1, ancla: "sup_der" }, b, -200, 100), 2);
  assert.equal(escalarDesdeAsa({ escala: 1, ancla: "sup_der" }, b, 200, -100), 0.05);
  // ancla abajo a la derecha: asa arriba a la izquierda; ir hacia el ancla achica
  assert.equal(escalarDesdeAsa({ escala: 1, ancla: "inf_der" }, b, 100, 50), 0.5);
  assert.equal(escalarDesdeAsa({ escala: 2, ancla: "sup_izq" }, b, 200, 100), 4);
  assert.equal(escalarDesdeAsa({ escala: 1 }, b, 100000, 50000), 5);
});

test("qué se toca: el asa y la caja de lo elegido primero; si no, la capa de arriba; si no, nada", () => {
  const doc = conFoto();
  const opciones = (seleccion) => ({ seleccion, materiales: MATS, medidasTexto: MEDIDAS, radioAsa: 30, margenAsa: 10 });
  // sin nada elegido, la foto (arriba) gana sobre el texto
  let g = gestoEn(doc, 1500, 540, 960, opciones(null));
  assert.deepEqual([g.tipo, g.id, g.alTocar], ["caja", "foto", "foto"]);
  assert.deepEqual(g.caja, { x: 140, y: 760, ancho: 800, alto: 400, ancla: "centro" });
  // con el texto elegido, arrastrar dentro de su caja lo mueve a él; tocar elige la de arriba
  g = gestoEn(doc, 1500, 540, 960, opciones("t1"));
  assert.deepEqual([g.tipo, g.id, g.alTocar], ["caja", "t1", "foto"]);
  assert.deepEqual(g.asa, { x: 840, y: 1020, sx: 1, sy: 1 });
  // su asa, aunque la foto esté encima
  g = gestoEn(doc, 1500, 855, 1030, opciones("t1"));
  assert.deepEqual([g.tipo, g.id, g.alTocar], ["asa", "t1", "t1"]);
  // fuera de la caja del texto pero sobre la foto: la foto
  g = gestoEn(doc, 1500, 200, 800, opciones("t1"));
  assert.deepEqual([g.tipo, g.id, g.alTocar, g.asa], ["caja", "foto", "foto", null]);
  // lienzo vacío
  g = gestoEn(doc, 1500, 10, 10, opciones("t1"));
  assert.deepEqual(g, { tipo: "vacio", id: null, alTocar: null, caja: null, asa: null });
  // el video elegido en la línea no es una capa: tocar el lienzo vacío es vacío
  assert.equal(gestoEn(doc, 1500, 10, 10, opciones("v0")).tipo, "vacio");
  // fuera de su tiempo el texto no está: ni su asa
  assert.equal(gestoEn(doc, 3500, 840, 1020, opciones("t1")).tipo, "vacio");
});

test("arrastrar da el cambio listo para operaciones.cambiar, redondeado", () => {
  assert.deepEqual(cambiosArrastre({ tipo: "caja", transform: { x: 0.49, y: 0.5 }, formato: "9:16" }, 0, 2),
    { cambios: { transform: { x: 0.5, y: 0.5 } }, guias: { vertical: true, horizontal: true } });
  assert.deepEqual(cambiosArrastre({ tipo: "caja", transform: { x: 0.1, y: 0.1 }, formato: "9:16" }, 100, 0),
    { cambios: { transform: { x: 0.1926, y: 0.1 } }, guias: { vertical: false, horizontal: false } });
  assert.deepEqual(cambiosArrastre({ tipo: "asa", transform: { escala: 1 }, caja: { ancho: 200, alto: 100 }, formato: "9:16" }, 100, 50),
    { cambios: { transform: { escala: 2 } }, guias: { vertical: false, horizontal: false } });
  const r = cambiosArrastre({ tipo: "asa", transform: { escala: 1 }, caja: { ancho: 300, alto: 100 }, formato: "9:16" }, 100, 0);
  assert.equal(r.cambios.transform.escala, Math.round(Math.hypot(250, 50) / Math.hypot(150, 50) * 1e4) / 1e4);
});

test("doble toque: mismo clip, cerca y rápido", () => {
  const antes = { t: 1000, x: 100, y: 100, id: "t1" };
  assert.equal(esDobleToque(antes, { t: 1300, x: 110, y: 105, id: "t1" }), true);
  assert.equal(esDobleToque(antes, { t: 1500, x: 100, y: 100, id: "t1" }), false);   // muy lento
  assert.equal(esDobleToque(antes, { t: 1200, x: 200, y: 100, id: "t1" }), false);   // muy lejos
  assert.equal(esDobleToque(antes, { t: 1200, x: 100, y: 100, id: "foto" }), false); // otro clip
  assert.equal(esDobleToque(null, { t: 1200, x: 100, y: 100, id: "t1" }), false);
  assert.equal(esDobleToque({ ...antes, id: null }, { t: 1200, x: 100, y: 100, id: null }), false);
  assert.equal(esDobleToque(antes, { t: 900, x: 100, y: 100, id: "t1" }), false);    // reloj hacia atrás
});

test("arrastrar empieza pasado un umbral (más grande con el dedo)", () => {
  assert.equal(superaUmbral(3, 0, "mouse"), false);
  assert.equal(superaUmbral(4, 0, "mouse"), true);
  assert.equal(superaUmbral(0, -4, "pen"), true);
  assert.equal(superaUmbral(5, 5, "touch"), false);
  assert.equal(superaUmbral(8, 0, "touch"), true);
});

test("cursor, porcentajes y tipo de clip para la capa del DOM", () => {
  assert.equal(cursorEn({ tipo: "asa", asa: { sx: 1, sy: 1 } }), "nwse-resize");
  assert.equal(cursorEn({ tipo: "asa", asa: { sx: -1, sy: -1 } }), "nwse-resize");
  assert.equal(cursorEn({ tipo: "asa", asa: { sx: -1, sy: 1 } }), "nesw-resize");
  assert.equal(cursorEn({ tipo: "caja" }), "move");
  assert.equal(cursorEn({ tipo: "vacio" }), "");
  assert.equal(cursorEn(null), "");
  assert.deepEqual(porcentaje({ x: 270, y: 480, ancho: 540, alto: 960 }, "9:16"), { left: 25, top: 25, width: 50, height: 50 });
  assert.deepEqual(porcentaje({ x: 1080, y: 0 }, "9:16"), { left: 100, top: 0, width: 0, height: 0 });
  const doc = docBase();
  assert.equal(esTexto(doc, "t1"), true);
  assert.equal(esTexto(doc, "v0"), false);
  assert.equal(esTexto(doc, "nada"), false);
  assert.equal(esTexto(null, "t1"), false);
});

// ---- Task 8, arreglo 1: imán en px de pantalla y asa de una capa chica ----
import { IMAN_PX } from "../../static/editor/seleccion.js";

test("el imán del centro se mide en px de pantalla: con el dedo en un reproductor chico también pega", () => {
  const proporcion = 6.5;                                  // px del lienzo por px de pantalla (celular)
  const g = { tipo: "caja", transform: { x: 0.3, y: 0.3 }, formato: "9:16", iman: IMAN_PX * proporcion };
  // termina a 5 px de pantalla (32,5 px del lienzo) del centro: pega y muestra las guías
  assert.deepEqual(cambiosArrastre(g, 540 - 32.5 - 324, 960 - 32.5 - 576),
    { cambios: { transform: { x: 0.5, y: 0.5 } }, guias: { vertical: true, horizontal: true } });
  // a 12 px de pantalla (78 del lienzo) no pega
  assert.deepEqual(cambiosArrastre(g, 540 - 78 - 324, 960 - 78 - 576),
    { cambios: { transform: { x: 0.4278, y: 0.4594 } }, guias: { vertical: false, horizontal: false } });
  // sin `iman` queda el de moverCapa (12 px del lienzo): a 5 px de pantalla no pegaría
  const sinIman = cambiosArrastre({ ...g, iman: undefined }, 540 - 32.5 - 324, 960 - 32.5 - 576);
  assert.deepEqual(sinIman.guias, { vertical: false, horizontal: false });
});

test("en una capa chica el asa no se come la caja: tocar adentro mueve", () => {
  const doc = conFoto();
  const mats = { 3: { ancho: 100, alto: 40 } };            // caja 490..590 × 940..980, asa en (590, 980)
  const op = { seleccion: "foto", materiales: mats, medidasTexto: MEDIDAS, radioAsa: 18 * 6.5, margenAsa: 8 * 6.5 };
  assert.deepEqual(cajaElegida(doc, 1500, "foto", mats, {}), { x: 490, y: 940, ancho: 100, alto: 40, ancla: "centro" });
  // adentro, a 33 px de la esquina: antes era el asa (radio 117), ahora mueve la foto
  let g = gestoEn(doc, 1500, 560, 965, op);
  assert.deepEqual([g.tipo, g.id], ["caja", "foto"]);
  // adentro y pegado a la esquina (radio tope 0,35 × 40 = 14): el asa
  g = gestoEn(doc, 1500, 582, 972, op);
  assert.deepEqual([g.tipo, g.id], ["asa", "foto"]);
  // afuera de la caja, cerca de la esquina: el asa con su radio entero (aunque haya otra capa debajo)
  g = gestoEn(doc, 1500, 620, 1000, op);
  assert.deepEqual([g.tipo, g.id], ["asa", "foto"]);
  // una capa grande no cambia: el radio entero también adentro
  g = gestoEn(doc, 1500, 820, 1000, { ...op, seleccion: "t1" });
  assert.deepEqual([g.tipo, g.id], ["asa", "t1"]);
});
