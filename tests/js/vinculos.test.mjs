// Editor capa 5b (Tarea 2, D10): «todo sigue a su clip». El algoritmo exacto
// está en la spec §2.4; estas pruebas lo siguen caso por caso sobre
// docVinculos() (docBase() + un segundo texto t2 que choca con t1 al
// seguir, y una música m1 que nunca sigue pero sí se recorta).
import { test } from "node:test";
import assert from "node:assert/strict";
import * as op from "../../static/editor/operaciones.js";
import * as vinc from "../../static/editor/vinculos.js";
import { duracionMs } from "../../static/editor/tiempo.js";
import { vocesJuntas } from "../../static/editor/avisos_carga.js";
import { conLasPistasLlenas, docVinculos, DURACIONES as D } from "./doc_base.mjs";

function buscar(doc, id) {
  for (const pista of doc.pistas) {
    const clip = pista.clips.find((c) => c.id === id);
    if (clip) return { clip, pista: pista.id };
  }
  return null;
}
const inicioDe = (doc, id) => buscar(doc, id)?.clip.inicio_ms;
const pistaDe = (doc, id) => buscar(doc, id)?.pista;

// Ninguna de las dos entradas se toca: se clonan antes de llamar y se
// comparan campo a campo después. Todas las pruebas de seguirPrincipal pasan
// por aquí.
function sinMutar(antes, despues, llamar) {
  const antesClon = structuredClone(antes);
  const despuesClon = structuredClone(despues);
  const resultado = llamar();
  assert.deepEqual(antes, antesClon, "seguirPrincipal no debe tocar `antes`");
  assert.deepEqual(despues, despuesClon, "seguirPrincipal no debe tocar `despues`");
  return resultado;
}

const seguir = (antes, despues, info = D) => sinMutar(antes, despues, () => vinc.seguirPrincipal(antes, despues, info));

// ---- sigue (D10.1) --------------------------------------------------------

test("sigue: textos, imágenes, superpuesto y audio de voz/efecto/subida/grabación; no la principal, p_sonido, música ni por_destino", () => {
  const doc = docVinculos();
  const principal = doc.pistas[0];
  const pTexto = { tipo: "texto" };
  const pImagen = { tipo: "imagen" };
  const pSuperpuesto = { tipo: "superpuesto" };
  const pAudio = { tipo: "audio", id: "p_voz" };
  const pSonido = { tipo: "audio", id: "p_sonido" };
  assert.equal(vinc.sigue(pTexto, {}, principal), true);
  assert.equal(vinc.sigue(pImagen, {}, principal), true);
  assert.equal(vinc.sigue(pSuperpuesto, {}, principal), true);
  for (const rol of ["voz", "efecto", "subida", "grabacion"]) {
    assert.equal(vinc.sigue(pAudio, { rol_audio: rol }, principal), true, rol);
  }
  assert.equal(vinc.sigue(pAudio, { rol_audio: "musica" }, principal), false);
  assert.equal(vinc.sigue(pSonido, { rol_audio: "sonido" }, principal), false);
  assert.equal(vinc.sigue(principal, principal.clips[0], principal), false);
  assert.equal(vinc.sigue(pAudio, { rol_audio: "voz", por_destino: { es: { material_id: 2, duracion_ms: 3000 } } }, principal), false);
});

// ---- anclas (D10.2) --------------------------------------------------------

test("anclas: el clip de la principal que suena en el inicio de cada capa que sigue, con su momento y su desfase", () => {
  const mapa = vinc.anclas(docVinculos());
  assert.deepEqual(mapa.get("t1"), { principalId: "v0", f: 1000, desfase: 1000 });
  assert.deepEqual(mapa.get("t2"), { principalId: "v1", f: 5000, desfase: 1000 });
  assert.deepEqual(mapa.get("a1"), { principalId: "v0", f: 0, desfase: 0 });
  assert.equal(mapa.has("m1"), false, "la música no sigue: no tiene ancla");
  assert.equal(mapa.has("s0"), false, "p_sonido no sigue: no tiene ancla");
});

// ---- seguirPrincipal: los casos de la spec (Tarea 2, Step 1) -------------

test("borrar(v0): t1 sigue en 1000, t2 cae ahí también y se reparte a una fila nueva, a1 en 0, la música se corta al nuevo fin", () => {
  const antes = docVinculos();
  const despues = op.borrar(antes, "v0", D).doc;
  const res = seguir(antes, despues);
  assert.equal(inicioDe(res, "t1"), 1000);
  assert.equal(pistaDe(res, "t1"), "p_texto");
  assert.equal(inicioDe(res, "t2"), 1000);
  assert.equal(pistaDe(res, "t2"), "p_texto_2", "t2 pisaba a t1 (que no se movió): se reparte a una fila nueva");
  assert.equal(inicioDe(res, "a1"), 0);
  const m1 = buscar(res, "m1").clip;
  assert.equal(m1.duracion_ms, 4000);
  assert.deepEqual(m1.recorte, { desde_ms: 0, hasta_ms: 4000 });
  assert.equal(duracionMs(res), 4000);
});

test("moverPrincipal(v1, 0): t1, t2 y a1 siguen a su clip, que cambió de lugar; la música no se toca (el fin no cambió)", () => {
  const antes = docVinculos();
  const despues = op.moverPrincipal(antes, "v1", 0, D).doc;
  const res = seguir(antes, despues);
  assert.equal(inicioDe(res, "t1"), 5000);
  assert.equal(inicioDe(res, "t2"), 1000);
  assert.equal(inicioDe(res, "a1"), 4000);
  assert.equal(pistaDe(res, "t1"), "p_texto");
  assert.equal(pistaDe(res, "t2"), "p_texto");
  assert.deepEqual(buscar(res, "m1").clip, buscar(antes, "m1").clip);
});

test('recortar(v0, "inicio", 1000): t1 sigue su momento al nuevo 0, a1 queda al borde (su momento ya no se ve), t2 sigue a v1, la música se corta', () => {
  const antes = docVinculos();
  const despues = op.recortar(antes, "v0", "inicio", 1000, D).doc;
  const res = seguir(antes, despues);
  assert.equal(inicioDe(res, "t1"), 0);
  assert.equal(inicioDe(res, "a1"), 0);
  assert.equal(inicioDe(res, "t2"), 4000);
  const m1 = buscar(res, "m1").clip;
  assert.equal(m1.duracion_ms, 7000);
  assert.deepEqual(m1.recorte, { desde_ms: 0, hasta_ms: 7000 });
});

test("cambiarVelocidad(v0, 2): el momento de t1 ahora suena al doble de rápido, a1 no se mueve, la música se corta al nuevo fin (6000)", () => {
  const antes = docVinculos();
  const despues = op.cambiarVelocidad(antes, "v0", 2, D).doc;
  const res = seguir(antes, despues);
  assert.equal(inicioDe(res, "t1"), 500);
  assert.equal(inicioDe(res, "t2"), 3000);
  assert.equal(inicioDe(res, "a1"), 0);
  const m1 = buscar(res, "m1").clip;
  assert.equal(m1.duracion_ms, 6000);
  assert.deepEqual(m1.recorte, { desde_ms: 0, hasta_ms: 6000 });
});

test("cortarEn(2000): ninguna capa cambia de lugar — el resultado es igual, campo a campo, a `despues`", () => {
  const antes = docVinculos();
  const despues = op.cortarEn(antes, 2000, D).doc;
  const res = seguir(antes, despues);
  assert.deepEqual(res, despues);
});

test("cortarEn(2000) y después borrar(v0_2), vinculado en cada paso: t3 sigue a la mitad nueva de su misma raíz, y tras el borrado cae por cierre + desfase sin cambiar de fila", () => {
  const T = { x: 0.5, y: 0.5, escala: 1, rotacion: 0, opacidad: 1, ancla: "centro" };
  const conT3 = () => {
    const d = docVinculos();
    d.pistas.push({
      id: "p_titulos", tipo: "texto", bloqueada: false, silenciada: false, oculta: false, clips: [
        { id: "t3", inicio_ms: 2500, duracion_ms: 300, texto: { literal: "Oferta" }, estilo: { fuente: "Inter-Bold" },
          transform: { ...T }, keyframes: [], animacion: null },
      ],
    });
    return d;
  };

  const doc0 = conT3();
  const despues1 = op.cortarEn(doc0, 2000, D).doc;
  const res1 = seguir(doc0, despues1);
  assert.equal(inicioDe(res1, "t3"), 2500, "sigue a v0_2, la mitad nueva de la misma raíz que v0");
  assert.equal(pistaDe(res1, "t3"), "p_titulos");

  const despues2 = op.borrar(res1, "v0_2", D).doc;
  const res2 = seguir(res1, despues2);
  assert.equal(inicioDe(res2, "t1"), 1000);
  assert.equal(inicioDe(res2, "t3"), 2500, "cierre (2000, donde ahora empieza v1) + desfase (500)");
  assert.equal(pistaDe(res2, "t3"), "p_titulos", "sin cambiar de fila: no pisa a nadie ahí");
  assert.equal(inicioDe(res2, "t2"), 3000);
  const m1 = buscar(res2, "m1").clip;
  assert.equal(m1.duracion_ms, 6000);
  assert.deepEqual(m1.recorte, { desde_ms: 0, hasta_ms: 6000 });
});

test("agregarVideo al principio: t1, a1 y t2 siguen a su clip, corrido; la música no se toca (el fin creció)", () => {
  const antes = docVinculos();
  const INFO = { 1: { duracion_ms: 8000, tiene_audio: true }, 2: { duracion_ms: 3000 }, 3: { duracion_ms: 1500, tiene_audio: false } };
  const despues = op.agregarVideo(antes, { id: 3 }, { indice: 0 }, INFO).doc;
  const res = seguir(antes, despues, INFO);
  assert.equal(inicioDe(res, "t1"), 2500);
  assert.equal(inicioDe(res, "a1"), 1500);
  assert.equal(inicioDe(res, "t2"), 6500);
  assert.deepEqual(buscar(res, "m1").clip, buscar(antes, "m1").clip);
});

test("duplicar(v0): t1 sigue en el v0 original (no en la copia), t2 sigue a v1 corrido", () => {
  const antes = docVinculos();
  const despues = op.duplicar(antes, "v0", D).doc;
  const res = seguir(antes, despues);
  assert.equal(inicioDe(res, "t1"), 1000);
  assert.equal(inicioDe(res, "t2"), 9000);
  assert.equal(inicioDe(res, "a1"), 0);
});

test("borrar(v1), el último clip: t2 no tenía a quién seguir y entra entera terminando en el fin nuevo (3000–4000); la música se corta a 4000", () => {
  const antes = docVinculos();
  const despues = op.borrar(antes, "v1", D).doc;
  const res = seguir(antes, despues);
  const t2 = buscar(res, "t2").clip;
  assert.equal(t2.inicio_ms, 3000);
  assert.equal(t2.duracion_ms, 1000);
  assert.equal(inicioDe(res, "t1"), 1000);
  const m1 = buscar(res, "m1").clip;
  assert.equal(m1.duracion_ms, 4000);
  assert.deepEqual(m1.recorte, { desde_ms: 0, hasta_ms: 4000 });
});

test("una voz con por_destino nunca sigue ni se corta: a1 no se mueve aunque la principal cambie de orden", () => {
  const antes = docVinculos();
  buscar(antes, "a1").clip.por_destino = { es: { material_id: 2, duracion_ms: 3000 } };
  const despues = op.moverPrincipal(antes, "v1", 0, D).doc;
  const res = seguir(antes, despues);
  assert.equal(inicioDe(res, "a1"), 0);
  assert.equal(pistaDe(res, "a1"), "p_voz");
});

test("si la principal no cambió, seguirPrincipal devuelve el MISMO documento (sin clonar)", () => {
  const antes = docVinculos();
  const despues = op.moverA(antes, "t1", 2000, D).doc;
  const res = seguir(antes, despues);
  assert.equal(res, despues, "misma referencia: nada que seguir");
});

test("guardia: si `despues` ya trae una capa movida a mano, seguirPrincipal no la vuelve a anclar", () => {
  const antes = docVinculos();
  const despues = op.borrar(antes, "v0", D).doc;
  buscar(despues, "t1").clip.inicio_ms = 2222;
  const res = seguir(antes, despues);
  assert.equal(inicioDe(res, "t1"), 2222, "la operación no la movió a esa posición: gana el arrastre");
});

test("dos voces: una grabación que termina sonando a la vez que a1 cae en una fila de voz nueva (no p_voz), y vocesJuntas lo avisa", () => {
  const antes = docVinculos();
  antes.pistas[2].clips.push({
    id: "r1", inicio_ms: 4500, duracion_ms: 2000, material_id: 2, rol_audio: "voz",
    recorte: { desde_ms: 0, hasta_ms: 2000 }, velocidad: 1, audio: { volumen: 1, fundido_entrada_ms: 0, fundido_salida_ms: 0, ducking: true },
  });
  const despues = op.borrar(antes, "v0", D).doc;
  const res = seguir(antes, despues);
  assert.equal(inicioDe(res, "r1"), 500);
  assert.notEqual(pistaDe(res, "r1"), "p_voz", "a1 sigue ahí: r1 se reparte a una fila nueva");
  assert.equal(pistaDe(res, "a1"), "p_voz");
  assert.deepEqual(res.pistas.find((p) => p.id === pistaDe(res, "r1")).tipo, "audio");
  assert.deepEqual(vocesJuntas(res), [{ t_ms: 500, ids: ["a1", "r1"] }]);
});

test("foto: el texto encima de una foto sigue su desfase (la foto no tiene tiempo de fuente); el de encima de un video sigue su momento de material", () => {
  const T = { x: 0.5, y: 0.5, escala: 1, rotacion: 0, opacidad: 1, ancla: "centro" };
  const docFoto = (f0Duracion, v0Inicio) => ({
    pistas: [
      { id: "p_video", tipo: "video", bloqueada: false, silenciada: false, oculta: false, clips: [
        { id: "f0", inicio_ms: 0, duracion_ms: f0Duracion, material_id: 4, foto: true,
          recorte: { desde_ms: 0, hasta_ms: f0Duracion }, velocidad: 1, transform: { ...T }, keyframes: [], animacion: null,
          transicion: null, ken_burns: null, audio: { volumen: 1, fundido_entrada_ms: 0, fundido_salida_ms: 0, ducking: true } },
        { id: "v0", inicio_ms: v0Inicio, duracion_ms: 4000, material_id: 1, recorte: { desde_ms: 0, hasta_ms: 4000 }, velocidad: 1,
          transform: { ...T }, keyframes: [], animacion: null, transicion: null, ken_burns: null,
          audio: { volumen: 1, fundido_entrada_ms: 0, fundido_salida_ms: 0, ducking: true } },
      ] },
      { id: "p_texto", tipo: "texto", bloqueada: false, silenciada: false, oculta: false, clips: [
        { id: "tf", inicio_ms: 1000, duracion_ms: 500, texto: { literal: "Foto" }, estilo: { fuente: "Inter-Bold" },
          transform: { ...T }, keyframes: [], animacion: null },
        { id: "tv", inicio_ms: 4000, duracion_ms: 500, texto: { literal: "Video" }, estilo: { fuente: "Inter-Bold" },
          transform: { ...T }, keyframes: [], animacion: null },
      ] },
    ],
  });
  const antes = docFoto(3000, 3000);
  const despues = docFoto(2000, 2000);
  const res = seguir(antes, despues, {});
  assert.equal(inicioDe(res, "tf"), 1000, "la foto encogió, pero el desfase de tf (1000) sigue mostrándose igual");
  assert.equal(inicioDe(res, "tv"), 3000, "v0 se corrió 1000 ms hacia atrás: tv lo sigue");
});

// ---- operar ----------------------------------------------------------------

test("operar: con vincular:false hace solo la operación; con vincular:true (por defecto) también sigue a la principal", () => {
  const antes = docVinculos();
  const sinVincular = vinc.operar(op.borrar, antes, ["v0"], D, { vincular: false });
  assert.equal(inicioDe(sinVincular.doc, "t2"), 5000, "sin vincular: borrar por sí solo no mueve el texto");
  const conVincular = vinc.operar(op.borrar, antes, ["v0"], D);
  assert.equal(inicioDe(conVincular.doc, "t2"), 1000, "con vincular (por defecto): sigue a su clip");
  assert.deepEqual(antes, docVinculos(), "operar no toca el documento de entrada");
});

// ---- «Vincular» en localStorage (D10.9) ------------------------------------

test("leerVincular: apagado solo con \"0\" guardado; cualquier otra cosa, nada, o un almacén que falla, es prendido", () => {
  assert.equal(vinc.leerVincular(null), true);
  assert.equal(vinc.leerVincular({ getItem: () => { throw new Error("roto"); } }), true);
  assert.equal(vinc.leerVincular({ getItem: () => "0" }), false);
  assert.equal(vinc.leerVincular({ getItem: () => "1" }), true);
  assert.equal(vinc.leerVincular({ getItem: () => null }), true);
});

test("guardarVincular nunca lanza, aunque el almacén falle", () => {
  assert.doesNotThrow(() => vinc.guardarVincular({ setItem: () => { throw new Error("roto"); } }, false));
  assert.doesNotThrow(() => vinc.guardarVincular(null, true));
  const almacen = new Map();
  vinc.guardarVincular({ setItem: (k, v) => almacen.set(k, v), getItem: (k) => almacen.get(k) ?? null }, true);
  assert.equal(almacen.get(vinc.CLAVE_VINCULAR), "1");
  vinc.guardarVincular({ setItem: (k, v) => almacen.set(k, v), getItem: (k) => almacen.get(k) ?? null }, false);
  assert.equal(almacen.get(vinc.CLAVE_VINCULAR), "0");
});

// Revisión final de la capa 5b (D10.6): con TODAS las pistas ocupadas
// (`MAX_PISTAS`: 8 hasta la capa 5c, 20 desde la prueba en vivo), una capa
// movida que pisa a otra de su fila «se queda en la suya» — antes
// `pistaLibre` → `pistaNueva` lanzaba «demasiadas pistas» y un borrado o un
// reordenamiento corriente se rechazaba con «Vincular» prendido.
function docPistasLlenas() {
  const d = conLasPistasLlenas(docVinculos());
  assert.equal(d.pistas.length, op.MAX_PISTAS);
  return d;
}

test("con todas las pistas ocupadas, una capa que pisa a otra se queda en su fila en vez de rechazar la operación (D10.6)", () => {
  const antes = docPistasLlenas();
  const res = vinc.operar(op.borrar, antes, ["v0"], D).doc;
  assert.equal(res.pistas.length, op.MAX_PISTAS);
  assert.deepEqual([inicioDe(res, "t1"), pistaDe(res, "t1")], [1000, "p_texto"]);
  assert.deepEqual([inicioDe(res, "t2"), pistaDe(res, "t2")], [1000, "p_texto"], "sin filas libres, t2 se queda en la suya");
  const reordenado = vinc.operar(op.moverPrincipal, antes, ["v1", 0], D).doc;
  assert.equal(reordenado.pistas[0].clips[0].id, "v1");
});

test("con pistas de sobra (9 a 19), la capa que pisa a otra pasa a una fila nueva — el tope ya no es 8 (capa 5c, prueba en vivo)", () => {
  // docVinculos tiene 5 pistas; con 8 las filas se acababan y t2 se quedaba pegada a t1
  let antes = docVinculos();
  for (let i = 0; i < 5; i++) antes = op.agregarImagen(antes, { id: 4, ancho: 600, alto: 400 }, 0, { duracionMs: 1000 }, D).doc;
  assert.ok(antes.pistas.length > 8 && antes.pistas.length < op.MAX_PISTAS, `${antes.pistas.length} pistas`);
  const res = vinc.operar(op.borrar, antes, ["v0"], D).doc;
  assert.equal(res.pistas.length, antes.pistas.length + 1, "t2 abre una fila de texto nueva");
  assert.deepEqual([inicioDe(res, "t1"), pistaDe(res, "t1")], [1000, "p_texto"]);
  assert.equal(inicioDe(res, "t2"), 1000);
  assert.notEqual(pistaDe(res, "t2"), "p_texto", "ya no se queda pegada a t1");
});

// ---- Revisión final de la capa 5b: el deslizador de la duración de una
// transición (un gesto con clave) daba un lugar distinto según el camino ----
// Un texto en 3600, dentro de v0 (0–4000). Fundido a 200, deslizar a 1000 y
// volver a 200 en UN gesto: encadenado paso a paso, el texto terminaba en
// 3800 (sobre v1); de 200 a 200 directo se queda en 3600.
function docTextoEn3600() {
  const d = docVinculos();
  d.pistas[1].clips[0].inicio_ms = 3600;   // t1
  d.pistas[1].clips[0].duracion_ms = 300;
  return d;
}
const CLAVE_TR = "v0:transicion";

function gesto(doc, pasos, info = D) {
  let g = null;
  for (const ms of pasos) {
    const r = vinc.operarGesto(op.ponerTransicion, doc, ["v0", "fundido", ms], info,
      { clave: CLAVE_TR, gesto: g, continua: g !== null });
    doc = r.doc;
    g = r.gesto;
  }
  return { doc, gesto: g };
}

test("un gesto con clave se deriva de su base: el lugar de una capa no depende del camino", () => {
  const base = docTextoEn3600();
  assert.equal(inicioDe(gesto(base, [200]).doc, "t1"), 3600);
  assert.equal(inicioDe(gesto(base, [200, 1000, 200]).doc, "t1"), 3600);
  const ida = gesto(base, [200, 1000]);
  assert.equal(inicioDe(ida.doc, "t1"), 2999, "sin lugar en v0 (dura 3000), queda en su último ms — nunca sobre v1");
  assert.equal(ida.gesto.base, base, "la base del gesto es el documento de antes del primer paso");
});

test("operarGesto sin clave, con otra clave o sin `continua` es vinculos.operar de siempre", () => {
  const base = docTextoEn3600();
  const r = vinc.operarGesto(op.ponerTransicion, base, ["v0", "fundido", 200], D, {});
  assert.deepEqual(r.doc, vinc.operar(op.ponerTransicion, base, ["v0", "fundido", 200], D).doc);
  assert.equal(r.gesto, null);
  const g = gesto(base, [200, 1000]).gesto;
  const otra = vinc.operarGesto(op.ponerTransicion, g.ultimo, ["v0", "fundido", 200], D, { clave: "otra", gesto: g, continua: true });
  assert.equal(otra.gesto.base, g.ultimo, "otra clave: la base es el documento actual");
  const cortada = vinc.operarGesto(op.ponerTransicion, g.ultimo, ["v0", "fundido", 200], D, { clave: CLAVE_TR, gesto: g, continua: false });
  assert.equal(cortada.gesto.base, g.ultimo, "sin `continua` (deshacer, guardado, otra racha): base nueva");
  const ajeno = vinc.operarGesto(op.ponerTransicion, docTextoEn3600(), ["v0", "fundido", 200], D, { clave: CLAVE_TR, gesto: g, continua: true });
  assert.notEqual(ajeno.gesto.base, g.base, "si el documento ya no es el último del gesto, base nueva");
  const apagado = vinc.operarGesto(op.ponerTransicion, g.ultimo, ["v0", "fundido", 200], D, { clave: CLAVE_TR, gesto: g, continua: true, vincular: false });
  assert.equal(apagado.gesto.base, g.ultimo, "cambiar «Vincular» a mitad del gesto también empieza otro");
});

test("una capa cuyo clip ya no muestra su momento queda en el último ms de ese clip, no en el inicio del siguiente", () => {
  const antes = op.ponerTransicion(docTextoEn3600(), "v0", "fundido", 200, D).doc;
  const despues = op.ponerTransicion(antes, "v0", "fundido", 1000, D).doc;
  const res = seguir(antes, despues);
  assert.equal(inicioDe(res, "t1"), 2999);
});
