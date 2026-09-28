import { test } from "node:test";
import assert from "node:assert/strict";
import {
  borrar, cambiarVelocidad, cortarEn, duplicar, idNuevo, MIN_CLIP_MS, moverA, moverPrincipal, normalizar,
  OperacionInvalida, recortar, VELOCIDADES,
} from "../../static/editor/operaciones.js";
import * as op from "../../static/editor/operaciones.js";
import { docBase, DURACIONES } from "./doc_base.mjs";

const principal = (d) => d.pistas[0].clips.map((c) => [c.id, c.inicio_ms, c.duracion_ms, c.recorte.desde_ms, c.recorte.hasta_ms]);
const sonido = (d) => d.pistas.find((p) => p.id === "p_sonido").clips.map((c) => [c.inicio_ms, c.duracion_ms, c.recorte.desde_ms]);
const invalida = (fn, re) => assert.throws(fn, (e) => e instanceof OperacionInvalida && re.test(e.message));

test("cortarEn parte el clip bajo el cabezal y deja corte seco entre las mitades", () => {
  const base = docBase();
  base.pistas[0].clips[0].transicion = { tipo: "fundido", duracion_ms: 300 };
  const { doc, seleccion } = cortarEn(base, 2000, DURACIONES);
  assert.deepEqual(principal(doc), [["v0", 0, 2000, 0, 2000], ["v0_2", 2000, 2000, 2000, 4000], ["v1", 4000, 4000, 4000, 8000]]);
  assert.equal(doc.pistas[0].clips[0].transicion, null);
  assert.deepEqual(doc.pistas[0].clips[1].transicion, { tipo: "fundido", duracion_ms: 300 });
  assert.equal(seleccion, "v0_2");
  assert.deepEqual(sonido(doc), [[0, 2000, 0], [2000, 2000, 2000], [4000, 4000, 4000]]);
  assert.equal(base.pistas[0].clips.length, 2, "no toca el documento de entrada");
});

test("cortarEn rechaza el borde y fuera de un clip", () => {
  invalida(() => cortarEn(docBase(), 50, DURACIONES), /borde/);
  invalida(() => cortarEn(docBase(), 4000, DURACIONES), /cabezal dentro/);
  invalida(() => cortarEn(docBase(), 9000, DURACIONES), /cabezal dentro/);
});

test("borrar en la principal corre lo que sigue y no deja la edición sin video", () => {
  const { doc, seleccion } = borrar(docBase(), "v0", DURACIONES);
  assert.deepEqual(principal(doc), [["v1", 0, 4000, 4000, 8000]]);
  assert.equal(seleccion, "v1");
  assert.deepEqual(sonido(doc), [[0, 4000, 4000]]);
  invalida(() => borrar(doc, "v1", DURACIONES), /al menos un clip/);
});

test("borrar un texto lo quita sin mover nada más; el sonido de la escena no se borra solo", () => {
  const { doc } = borrar(docBase(), "t1", DURACIONES);
  // capa 4b: terminar() borra las pistas no principales que quedan sin clips.
  assert.ok(!doc.pistas.some((p) => p.id === "p_texto"));
  assert.deepEqual(principal(doc), principal(docBase()));
  invalida(() => borrar(docBase(), "s0", DURACIONES), /sonido de la escena/);
  invalida(() => borrar(docBase(), "nada", DURACIONES), /ya no existe/);
});

test("duplicar pone la copia justo después", () => {
  const { doc, seleccion } = duplicar(docBase(), "v0", DURACIONES);
  assert.deepEqual(principal(doc).map((c) => c.slice(0, 3)), [["v0", 0, 4000], ["v0_2", 4000, 4000], ["v1", 8000, 4000]]);
  assert.equal(seleccion, "v0_2");
  const texto = duplicar(docBase(), "t1", DURACIONES).doc.pistas[1].clips;
  assert.deepEqual(texto.map((c) => [c.id, c.inicio_ms]), [["t1", 1000], ["t1_2", 3000]]);
});

test("recortar el fin acorta y corre; no pasa del material", () => {
  const corto = recortar(docBase(), "v0", "fin", -1000, DURACIONES).doc;
  assert.deepEqual(principal(corto), [["v0", 0, 3000, 0, 3000], ["v1", 3000, 4000, 4000, 8000]]);
  const largo = recortar(docBase(), "v1", "fin", 5000, DURACIONES).doc;       // v1 ya llega al final del clon
  assert.deepEqual(principal(largo)[1], ["v1", 4000, 4000, 4000, 8000]);
  const minimo = recortar(docBase(), "v0", "fin", -99999, DURACIONES).doc;
  assert.equal(minimo.pistas[0].clips[0].duracion_ms, MIN_CLIP_MS);
});

test("recortar el inicio mueve el punto de entrada de la fuente", () => {
  const atras = recortar(docBase(), "v1", "inicio", -500, DURACIONES).doc;
  assert.deepEqual(principal(atras)[1], ["v1", 4000, 4500, 3500, 8000]);
  const adelante = recortar(docBase(), "v0", "inicio", 1000, DURACIONES).doc;
  assert.deepEqual(principal(adelante), [["v0", 0, 3000, 1000, 4000], ["v1", 3000, 4000, 4000, 8000]]);
  const texto = recortar(docBase(), "t1", "inicio", -5000, DURACIONES).doc.pistas[1].clips[0];
  assert.deepEqual([texto.inicio_ms, texto.duracion_ms], [0, 3000]);
});

test("moverPrincipal reordena y moverA mueve capas sin pasar de 0", () => {
  const { doc } = moverPrincipal(docBase(), "v1", 0, DURACIONES);
  assert.deepEqual(principal(doc).map((c) => c.slice(0, 3)), [["v1", 0, 4000], ["v0", 4000, 4000]]);
  assert.deepEqual(sonido(doc), [[0, 4000, 4000], [4000, 4000, 0]]);
  assert.equal(moverA(docBase(), "t1", -300, DURACIONES).doc.pistas[1].clips[0].inicio_ms, 0);
  assert.equal(moverA(docBase(), "a1", 2500, DURACIONES).doc.pistas[2].clips[0].inicio_ms, 2500);
  invalida(() => moverA(docBase(), "v0", 100, DURACIONES), /pista principal/);
});

test("cambiarVelocidad conserva el tramo de fuente y quita el sonido de ese clip", () => {
  const { doc } = cambiarVelocidad(docBase(), "v0", 2, DURACIONES);
  assert.deepEqual(principal(doc), [["v0", 0, 2000, 0, 4000], ["v1", 2000, 4000, 4000, 8000]]);
  assert.equal(doc.pistas[0].clips[0].velocidad, 2);
  assert.deepEqual(sonido(doc), [[2000, 4000, 4000]]);
  invalida(() => cambiarVelocidad(docBase(), "v0", 3, DURACIONES), /velocidad/);
  invalida(() => cambiarVelocidad(docBase(), "t1", 2, DURACIONES), /video/);
});

test("cambiarVelocidad nunca pide más material del que hay (v1 ya llega al final del clon)", () => {
  for (const v of VELOCIDADES) {
    const { doc } = cambiarVelocidad(docBase(), "v1", v, DURACIONES);
    const clip = doc.pistas[0].clips.find((c) => c.id === "v1");
    assert.ok(clip.recorte.hasta_ms <= DURACIONES[1],
      `${v}×: recorte.hasta_ms ${clip.recorte.hasta_ms} pasa del material (${DURACIONES[1]})`);
    assert.ok(clip.duracion_ms >= MIN_CLIP_MS, `${v}×: duracion_ms ${clip.duracion_ms} < MIN_CLIP_MS`);
  }
});

test("normalizar acorta o quita la transición cuya cola no cabe en el material", () => {
  const d = docBase();
  d.pistas[0].clips[0].transicion = { tipo: "fundido", duracion_ms: 500 };
  d.pistas[0].clips[0].recorte = { desde_ms: 3700, hasta_ms: 7700 };
  normalizar(d, DURACIONES);
  assert.deepEqual(d.pistas[0].clips[0].transicion, { tipo: "fundido", duracion_ms: 300 });
  d.pistas[0].clips[0].recorte = { desde_ms: 4000, hasta_ms: 8000 };
  normalizar(d, DURACIONES);
  assert.equal(d.pistas[0].clips[0].transicion, null);
});

test("idNuevo da ids válidos y únicos", () => {
  const d = docBase();
  const id = idNuevo(d, "v0");
  assert.equal(id, "v0_2");
  const largo = idNuevo(d, "x".repeat(60));
  assert.ok(/^[A-Za-z0-9_-]{1,40}$/.test(largo), largo);
});

// ---- Redondeo: el render (Python) juzga con round-half-to-even ----
// `compilador.verificar_recortes` pide recorte.desde_ms + round(duracion_ms ×
// velocidad) <= material, con el round de Python (a la par). Math.round sube
// los .5: sin ajuste, las dos mitades de un corte (o un recorte del inicio)
// a velocidad ≠ 1 en un clip que llega al final del archivo piden 1 ms de más.
const redondeoPython = (x) => {
  const f = Math.floor(x);
  const r = x - f;
  if (r !== 0.5) return Math.round(x);
  return f % 2 === 0 ? f : f + 1;
};
const MATERIAL_9S = 9000;

// v1 a velocidad v, alargado hasta el final de un clon de 9 s.
function alFinalDelArchivo(v) {
  const D = { ...DURACIONES, 1: MATERIAL_9S };
  const conVel = cambiarVelocidad(docBase(), "v1", v, D).doc;
  return { doc: recortar(conVel, "v1", "fin", 99999, D).doc, D };
}

function cabeEnElMaterial(doc, D, contexto) {
  const p = doc.pistas[0];
  let t = 0;
  for (const c of p.clips) {
    assert.equal(c.inicio_ms, t, `${contexto}: la principal no quedó contigua en ${c.id}`);
    t += c.duracion_ms;
    assert.ok(c.duracion_ms >= MIN_CLIP_MS, `${contexto}: ${c.id} quedó de ${c.duracion_ms} ms`);
  }
  for (const pista of doc.pistas) {
    for (const c of pista.clips) {
      if (c.material_id === undefined || D[c.material_id] === undefined) continue;
      if (pista.tipo === "audio" && c.rol_audio === "musica") continue;
      const v = Number(c.velocidad ?? 1);
      const fin = (c.recorte?.desde_ms ?? 0) + redondeoPython(c.duracion_ms * v);
      assert.ok(fin <= D[c.material_id], `${contexto}: '${c.id}' pide ${fin} ms de un material de ${D[c.material_id]} ms`);
      assert.equal(c.recorte.hasta_ms, c.recorte.desde_ms + Math.round(c.duracion_ms * v), `${contexto}: recorte de ${c.id}`);
    }
  }
  const sonido = doc.pistas.find((x) => x.id === "p_sonido").clips;
  assert.deepEqual(sonido.map((c) => [c.inicio_ms, c.duracion_ms, c.recorte.desde_ms]),
    p.clips.filter((c) => Number(c.velocidad ?? 1) === 1).map((c) => [c.inicio_ms, c.duracion_ms, c.recorte.desde_ms]),
    `${contexto}: el sonido de la escena no sigue a la principal`);
}

test("un clip al final del archivo sigue cabiendo tras cortarlo, a cualquier velocidad", () => {
  for (const v of VELOCIDADES) {
    const { doc, D } = alFinalDelArchivo(v);
    const v1 = doc.pistas[0].clips[1];
    assert.equal(v1.recorte.desde_ms + Math.round(v1.duracion_ms * v), MATERIAL_9S, `${v}×: v1 no llega al final`);
    const desde = v1.inicio_ms + MIN_CLIP_MS;
    const hasta = v1.inicio_ms + v1.duracion_ms - MIN_CLIP_MS;
    for (let t = desde; t < hasta; t += (t < desde + 300 || t > hasta - 300 ? 1 : 7)) {
      cabeEnElMaterial(cortarEn(doc, t, D).doc, D, `${v}× corte en ${t}`);
    }
  }
});

test("recortar el inicio por cantidades impares no hace pedir material de más, a cualquier velocidad", () => {
  for (const v of VELOCIDADES) {
    const { doc, D } = alFinalDelArchivo(v);
    const largo = doc.pistas[0].clips[1].duracion_ms;
    for (let d = 1; d < largo - MIN_CLIP_MS; d += (d < 400 ? 2 : 37)) {
      cabeEnElMaterial(recortar(doc, "v1", "inicio", d, D).doc, D, `${v}× inicio +${d}`);
      cabeEnElMaterial(recortar(doc, "v1", "inicio", -d, D).doc, D, `${v}× inicio -${d}`);
    }
    // cortar primero y recortar el inicio de la segunda mitad (así se reportó: 'v1_2' pedía 8001 ms)
    const cortado = cortarEn(doc, doc.pistas[0].clips[1].inicio_ms + 1001, D).doc;
    for (let d = 1; d < 600; d += 2) {
      cabeEnElMaterial(recortar(cortado, "v1_2", "inicio", d, D).doc, D, `${v}× v1_2 inicio +${d}`);
    }
  }
});

test("normalizar acorta lo justo un clip que pide 1 ms de más (y nunca por debajo del mínimo)", () => {
  const d = docBase();
  const D = { 1: 8000, 2: 3000 };
  d.pistas[0].clips[1] = { ...d.pistas[0].clips[1], velocidad: 0.5, duracion_ms: 7999, recorte: { desde_ms: 4001, hasta_ms: 8001 } };
  normalizar(d, D);
  const v1 = d.pistas[0].clips[1];
  assert.deepEqual([v1.inicio_ms, v1.duracion_ms, v1.recorte.desde_ms, v1.recorte.hasta_ms], [4000, 7998, 4001, 8000]);
  const corto = docBase();
  corto.pistas[0].clips[1] = { ...corto.pistas[0].clips[1], velocidad: 0.5, duracion_ms: MIN_CLIP_MS, recorte: { desde_ms: 7951, hasta_ms: 8001 } };
  normalizar(corto, D);
  const c1 = corto.pistas[0].clips[1];
  assert.deepEqual([c1.duracion_ms, c1.recorte.desde_ms, c1.recorte.hasta_ms], [MIN_CLIP_MS, 7950, 8000]);
  const voz = docBase();
  voz.pistas[2].clips[0] = { ...voz.pistas[2].clips[0], duracion_ms: 3200, recorte: { desde_ms: 0, hasta_ms: 3200 } };
  normalizar(voz, D);
  assert.deepEqual([voz.pistas[2].clips[0].duracion_ms, voz.pistas[2].clips[0].recorte.hasta_ms], [3000, 3000]);
});

// ---- Voz por destino: resolver la cambia entera por la de cada país ----
function conVozPorDestino() {
  const d = docBase();
  d.pistas[2].clips[0].por_destino = { en_US: { material_id: 2, duracion_ms: 2600 } };
  return d;
}

test("recortar una voz que cambia por país se rechaza en español llano; moverla y borrarla sí se puede", () => {
  for (const lado of ["inicio", "fin"]) {
    invalida(() => recortar(conVozPorDestino(), "a1", lado, -300, DURACIONES),
      /^La voz se ajusta sola a cada país: puedes moverla o borrarla, pero no recortarla\.$/);
  }
  assert.equal(moverA(conVozPorDestino(), "a1", 500, DURACIONES).doc.pistas[2].clips[0].inicio_ms, 500);
  // capa 4b: terminar() borra las pistas no principales que quedan sin clips.
  assert.ok(!borrar(conVozPorDestino(), "a1", DURACIONES).doc.pistas.some((p) => p.id === "p_voz"));
  const vacio = docBase();
  vacio.pistas[2].clips[0].por_destino = {};                  // {} no distingue por destino: se recorta como siempre
  assert.equal(recortar(vacio, "a1", "fin", -500, DURACIONES).doc.pistas[2].clips[0].duracion_ms, 2500);
});

// ---- Capa 4b: agregar y cambiar ----
// `info` es el mapa nuevo {material_id: {duracion_ms, tiene_audio}} (el
// viejo {material_id: duracion_ms} sigue funcionando, ver el test de más
// abajo). Material 3: sin audio nativo (para ver que el espejo lo excluye).
const INFO = { 1: { duracion_ms: 8000, tiene_audio: true }, 2: { duracion_ms: 3000 }, 3: { duracion_ms: 1500, tiene_audio: false } };
const clipDe = (d, id) => d.pistas.flatMap((p) => p.clips).find((c) => c.id === id);

// Toda operación es pura (no toca el documento que recibe) y deja una
// `seleccion` que de verdad está en el documento resultante.
function puro(fn, base = docBase()) {
  const antes = structuredClone(base);
  const r = fn(base);
  assert.deepEqual(base, antes, "no debe tocar el documento de entrada");
  assert.notEqual(r.doc, base);
  assert.ok(clipDe(r.doc, r.seleccion), "la selección debe existir en el documento resultante");
  return r;
}

test("agregarVideo inserta el material entero después del clip dado y no espeja sonido si el material no trae", () => {
  const r = puro((d) => op.agregarVideo(d, { id: 3 }, { despuesDe: "v0" }, INFO));
  assert.deepEqual(principal(r.doc).map((c) => c.slice(1)), [[0, 4000, 0, 4000], [4000, 1500, 0, 1500], [5500, 4000, 4000, 8000]]);
  assert.equal(clipDe(r.doc, r.seleccion).material_id, 3);
  assert.equal(clipDe(r.doc, r.seleccion).ken_burns, null);
  assert.equal(r.doc.pistas.find((p) => p.id === "p_sonido").clips.length, 2);
  invalida(() => op.agregarVideo(docBase(), { id: 9 }, {}, INFO), /Ese video todavía se está preparando/);
  invalida(() => op.agregarVideo(docBase(), { id: 3 }, { despuesDe: "t1" }, INFO), /principal/);
});

test("agregarImagen usa las medidas naturales para cubrir o para el 60% del ancho, y reusa pista solo si no hay solape", () => {
  const material = { id: 4, ancho: 600, alto: 400 };
  const a = puro((d) => op.agregarImagen(d, material, 1000, {}, INFO));
  assert.equal(clipDe(a.doc, a.seleccion).transform.escala, 1.08);
  const b = puro((d) => op.agregarImagen(d, material, 2000, { llenar: true }, INFO), a.doc);
  assert.equal(clipDe(b.doc, b.seleccion).transform.escala, 4.8);
  assert.equal(b.doc.pistas.filter((p) => p.tipo === "imagen").length, 2);
  const c = op.agregarImagen(a.doc, material, 4000, {}, INFO);      // toca justo donde termina la primera: no hay solape
  assert.equal(c.doc.pistas.filter((p) => p.tipo === "imagen").length, 1);
});

test("agregarAudio toma la duración de la fuente entera y distingue el fundido de música del de efecto", () => {
  for (const rol of ["musica", "efecto"]) {
    const r = puro((d) => op.agregarAudio(d, { id: 2 }, 1000, { rol }, INFO));
    const c = clipDe(r.doc, r.seleccion);
    assert.deepEqual(c.recorte, { desde_ms: 0, hasta_ms: 3000 });
    assert.equal(c.audio.fundido_salida_ms, rol === "musica" ? 1000 : 0);
    assert.equal(c.rol_audio, rol);
  }
  invalida(() => op.agregarAudio(docBase(), { id: 2 }, 0, { rol: "voz" }, INFO), /rol/i);
});

test("agregarTexto usa tamaños fraccionarios del lienzo y el fondo de marca en el preset precio", () => {
  for (const [preset, px, y] of [["titulo", 72, 0.2], ["subtitulo", 48, 0.75], ["precio", 56, 0.6], ["llamado", 52, 0.85]]) {
    const r = puro((d) => op.agregarTexto(d, 500, preset, INFO));
    const c = clipDe(r.doc, r.seleccion);
    assert.equal(c.estilo.tamano, px / 1920);
    assert.equal(c.transform.y, y);
    assert.equal(c.texto.literal, preset === "precio" ? "$ 0" : "Escribe aquí");
    if (preset === "precio") assert.equal(c.estilo.fondo.color, "#7c3aed");
  }
  invalida(() => op.agregarTexto(docBase(), 0, "otro", INFO), /texto/i);
});

test("cortarClip parte el recorte en audio, solo el tiempo en texto (y copia el png), sin tocar la principal aparte", () => {
  const a = puro((d) => op.cortarClip(d, "a1", 1000, INFO));
  assert.deepEqual(clipDe(a.doc, a.seleccion).recorte, { desde_ms: 1000, hasta_ms: 3000 });
  assert.equal(clipDe(a.doc, a.seleccion).inicio_ms, 1000);
  const base = docBase();
  base.pngs = { t1: 20 };
  const t = puro((d) => op.cortarClip(d, "t1", 2000, INFO), base);
  assert.equal(t.doc.pngs[t.seleccion], 20);
  assert.equal(clipDe(t.doc, t.seleccion).duracion_ms, 1000);
  invalida(() => op.cortarClip(docBase(), "a1", 50, INFO), /borde/);
  invalida(() => op.cortarClip(conVozPorDestino(), "a1", 1000, INFO), /país/);
  invalida(() => op.cortarClip(docBase(), "s0", 1000, INFO), /sonido/);
});

test("ponerTransicion normaliza la cola contra el material y rechaza el último clip o uno fuera de la principal", () => {
  for (const tipo of ["corte", "fundido", "deslizar", "zoom", "desenfoque"]) {
    const r = puro((d) => op.ponerTransicion(d, "v0", tipo, 500, INFO));
    assert.deepEqual(clipDe(r.doc, "v0").transicion, tipo === "corte" ? null : { tipo, duracion_ms: 500 });
  }
  invalida(() => op.ponerTransicion(docBase(), "v1", "fundido", 500, INFO), /último/);
  invalida(() => op.ponerTransicion(docBase(), "t1", "fundido", 500, INFO), /principal/);
  invalida(() => op.ponerTransicion(docBase(), "v0", "inventada", 500, INFO), /transición/);
});

test("editarTexto guarda solo el destino pedido, conserva los demás y borra todo png que use esa variable", () => {
  const base = docBase();
  base.pistas[1].clips[0].texto = { variable: "gancho" };
  base.variables.textos = { gancho: { es: "Hola", en_US: "Hello" } };
  const dup = duplicar(base, "t1", INFO).doc;
  dup.pngs = { t1: 20, t1_2: 21 };
  const r = puro((d) => op.editarTexto(d, "t1", "Oferta", "es_CO", INFO), dup);
  assert.deepEqual(r.doc.variables.textos.gancho, { es: "Hola", en_US: "Hello", es_CO: "Oferta" });
  assert.deepEqual(r.doc.pngs, {});          // t1 Y t1_2 comparten la variable: los dos se invalidan
  assert.equal(clipDe(puro((d) => op.editarTexto(d, "t1", "Nuevo", "es", INFO)).doc, "t1").texto.literal, "Nuevo");
  invalida(() => op.editarTexto(base, "t1", " ", "es", INFO), /El texto no puede quedar vacío/);
  invalida(() => op.editarTexto(base, "t1", "x", "wrong", INFO), /destino/);
});

test("cambiar acota los campos editables, guarda el tamaño como fracción, rechaza claves de más y borra el png del texto", () => {
  const base = docBase();
  base.pngs = { t1: 20 };
  const r = puro((d) => op.cambiar(d, "t1", {
    estilo: { tamano: 400, color: "#123456" },
    transform: { x: -1, y: 2, escala: 9, opacidad: 2 },
    animacion: { entrada: "deslizar" },
  }, INFO), base);
  assert.equal(clipDe(r.doc, "t1").estilo.tamano, 200 / 1920);
  assert.equal(clipDe(r.doc, "t1").transform.escala, 5);
  assert.equal(clipDe(r.doc, "t1").transform.x, 0);
  assert.deepEqual(r.doc.pngs, {});
  for (const cambios of [
    { material_id: 9 }, { transform: { rotacion: 45 } }, { estilo: { fuente: "Arial" } },
    { animacion: { entrada: "rebote" } }, { audio: { volumen: NaN } }, { estilo: { fondo: { unexpected: 1 } } },
  ]) invalida(() => op.cambiar(base, "t1", cambios, INFO), /./);
});

test("cambiar: transform solo en clips que lo tienen (un clip de audio, o el espejo de sonido, se rechaza en español llano)", () => {
  invalida(() => op.cambiar(docBase(), "a1", { transform: { x: 0.3 } }, INFO), /audio/i);
  invalida(() => op.cambiar(docBase(), "s0", { transform: { x: 0.3 } }, INFO), /audio/i);
});

test("cambiar: un contorno/sombra/fondo parcial conserva los campos que no se tocan (y null los sigue quitando)", () => {
  const base = docBase();
  base.pistas[1].clips[0].estilo = {
    ...base.pistas[1].clips[0].estilo,
    contorno: { color: "#ABCDEF", grosor: 0.01 },
    sombra: { color: "#112233", dx: 0.02, dy: 0.03 },
    fondo: { color: "#445566", opacidad: 0.5, radio: 0.1, relleno_x: 0.02, relleno_y: 0.02, ancho: 0.4 },
  };
  const r1 = puro((d) => op.cambiar(d, "t1", { estilo: { contorno: { grosor: 0.03 } } }, INFO), base);
  assert.deepEqual(clipDe(r1.doc, "t1").estilo.contorno, { color: "#ABCDEF", grosor: 0.03 });
  const r2 = op.cambiar(base, "t1", { estilo: { sombra: { dx: 0.05 } } }, INFO);
  assert.deepEqual(clipDe(r2.doc, "t1").estilo.sombra, { color: "#112233", dx: 0.05, dy: 0.03 });
  const r3 = op.cambiar(base, "t1", { estilo: { fondo: { opacidad: 0.9 } } }, INFO);
  assert.deepEqual(clipDe(r3.doc, "t1").estilo.fondo,
    { color: "#445566", opacidad: 0.9, radio: 0.1, relleno_x: 0.02, relleno_y: 0.02, ancho: 0.4 });
  // null sigue siendo "sin contorno": el contrato de hoy, sin cambiar.
  assert.equal(op.cambiar(base, "t1", { estilo: { contorno: null } }, INFO).doc.pistas[1].clips[0].estilo.contorno, null);
});

test("el volumen del sonido de la escena queda por clip al normalizar y un corte nuevo hereda solo su propio sonido", () => {
  let d = normalizar(docBase(), INFO);
  d = op.volumenSonido(d, "v0", 0.2, INFO).doc;
  d = op.volumenSonido(d, "v1", 0.8, INFO).doc;
  const r = puro((x) => op.cortarClip(x, "v0", 2000, INFO), d);
  assert.equal(clipDe(r.doc, "s_v0").audio.volumen, 0.2);
  assert.equal(clipDe(r.doc, `s_${r.seleccion}`).audio.volumen, 0.2);
  assert.equal(clipDe(r.doc, "s_v1").audio.volumen, 0.8);
  // v0 y v1 a velocidad ≠ 1: nada que espejar, p_sonido desaparece; al volver v0 a 1×, vuelve a aparecer.
  const mudo = op.cambiarVelocidad(op.cambiarVelocidad(d, "v0", 2, INFO).doc, "v1", 2, INFO).doc;
  assert.ok(!mudo.pistas.some((p) => p.id === "p_sonido"));
  assert.ok(op.cambiarVelocidad(mudo, "v0", 1, INFO).doc.pistas.some((p) => p.id === "p_sonido"));
});

test("el mapa de info rico da exactamente el mismo resultado que el mapa viejo de números", () => {
  assert.deepEqual(recortar(docBase(), "v1", "fin", 99999, INFO).doc, recortar(docBase(), "v1", "fin", 99999, DURACIONES).doc);
  assert.deepEqual(cambiarVelocidad(docBase(), "v1", 1.5, INFO).doc, cambiarVelocidad(docBase(), "v1", 1.5, DURACIONES).doc);
});
