import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  activo, capasEn, duracionMs, fuenteMs, pistaPrincipal, posicionCapa, principalEn,
  siguienteClip, transicionReal, zoomKenBurns,
} from "../../static/editor/tiempo.js";

// El documento de las pruebas del compilador: c1 0–3500 con fundido de 500
// hacia c2 3500–7000, texto t1 200–2700 con entrada «deslizar» de 300 ms.
const DOC = JSON.parse(readFileSync(new URL("../fixtures/documentos/video_basico.json", import.meta.url), "utf8"));
const cerca = (a, b, msg) => assert.ok(Math.abs(a - b) < 1e-9, `${msg}: ${a} != ${b}`);

test("duración y pista principal", () => {
  assert.equal(duracionMs(DOC), 7000);
  assert.equal(pistaPrincipal(DOC).id, DOC.pistas[0].id);
  const soloImagen = { pistas: [{ id: "p", tipo: "imagen", clips: [{ id: "i", inicio_ms: 0, duracion_ms: 0 }] }] };
  assert.equal(pistaPrincipal(soloImagen).id, "p");
  assert.equal(pistaPrincipal({ pistas: [] }), null);
});

test("activo es [inicio, fin)", () => {
  const c = { inicio_ms: 100, duracion_ms: 50 };
  assert.ok(activo(c, 100) && activo(c, 149) && !activo(c, 150) && !activo(c, 99));
});

test("transicionReal ignora cortes y duraciones 0", () => {
  assert.equal(transicionReal({ transicion: null }), null);
  assert.equal(transicionReal({ transicion: { tipo: "corte", duracion_ms: 500 } }), null);
  assert.equal(transicionReal({ transicion: { tipo: "fundido", duracion_ms: 0 } }), null);
  assert.equal(transicionReal({ transicion: { tipo: "fundido", duracion_ms: 500 } }).tipo, "fundido");
});

test("fuenteMs aplica recorte y velocidad", () => {
  const c = { inicio_ms: 1000, duracion_ms: 2000, recorte: { desde_ms: 5000, hasta_ms: 7000 }, velocidad: 2 };
  assert.equal(fuenteMs(c, 1500), 6000);
});

test("principalEn: un solo clip fuera de la transición", () => {
  const r = principalEn(DOC, 1000);
  assert.equal(r.capas.length, 1);
  assert.equal(r.capas[0].clip.id, "c1");
  assert.equal(r.capas[0].fuenteMs, 1000);
  assert.equal(r.aproximada, false);
});

test("principalEn: el fundido ocupa [fin_A, fin_A + d) con la cola de A", () => {
  const r = principalEn(DOC, 3600);
  assert.deepEqual(r.capas.map((c) => c.clip.id), ["c1", "c2"]);
  assert.equal(r.capas[0].fuenteMs, 3600);          // cola de A, más allá de su hasta_ms
  assert.equal(r.capas[1].fuenteMs, 3600);
  cerca(r.capas[1].alfa, 0.2, "B entra con alfa = avance");
  assert.equal(r.capas[0].dx, 0);
  const despues = principalEn(DOC, 4000);
  assert.deepEqual(despues.capas.map((c) => c.clip.id), ["c2"]);
});

test("principalEn: deslizar mueve A a la izquierda y trae B desde la derecha", () => {
  const doc = structuredClone(DOC);
  doc.pistas[0].clips[0].transicion = { tipo: "deslizar", duracion_ms: 500 };
  const r = principalEn(doc, 3750);
  cerca(r.capas[0].dx, -0.5, "A");
  cerca(r.capas[1].dx, 0.5, "B");
  assert.equal(r.capas[1].alfa, 1);
  assert.equal(r.aproximada, false);
});

test("principalEn: zoom y desenfoque se ven como fundido aproximado", () => {
  for (const tipo of ["zoom", "desenfoque"]) {
    const doc = structuredClone(DOC);
    doc.pistas[0].clips[0].transicion = { tipo, duracion_ms: 500 };
    const r = principalEn(doc, 3600);
    assert.equal(r.aproximada, true, tipo);
    cerca(r.capas[1].alfa, 0.2, `fundido (${tipo})`);
  }
});

test("principalEn: después del último clip se congela su último cuadro", () => {
  const doc = structuredClone(DOC);
  doc.pistas.push({ id: "p_voz_larga", tipo: "audio", clips: [{ id: "vl", inicio_ms: 0, duracion_ms: 9000, material_id: 2 }] });
  const r = principalEn(doc, 8000);
  assert.equal(r.capas[0].clip.id, "c2");
  cerca(r.capas[0].fuenteMs, 7000 - 1000 / 30, "último cuadro");
});

test("principalEn: el cuadro congelado respeta la velocidad", () => {
  const doc = {
    pistas: [
      { id: "p_video", tipo: "video", clips: [
        { id: "c1", inicio_ms: 0, duracion_ms: 3000, recorte: { desde_ms: 0, hasta_ms: 6000 }, velocidad: 2 },
      ] },
      { id: "p_voz", tipo: "audio", clips: [{ id: "a1", inicio_ms: 0, duracion_ms: 4000, material_id: 2 }] },
    ],
  };
  const r = principalEn(doc, 3500);
  cerca(r.capas[0].fuenteMs, (3000 - 1000 / 30) * 2, "fuente a doble velocidad");
  cerca(r.capas[0].tZoom, 3000 - 1000 / 30, "instante congelado, sin escalar por velocidad");
});

test("principalEn: pista principal imagen no tiene instante de zoom", () => {
  const doc = { pistas: [{ id: "p", tipo: "imagen", clips: [{ id: "i", inicio_ms: 0, duracion_ms: 0 }] }] };
  const r = principalEn(doc, 1234);
  assert.equal(r.capas[0].tZoom, null);
});

test("siguienteClip devuelve el próximo clip de la principal", () => {
  assert.equal(siguienteClip(DOC, 3000).id, "c2");
  assert.equal(siguienteClip(DOC, 5000), null);
});

test("zoomKenBurns sigue al zoompan del compilador (1.0 → 1.08)", () => {
  const c = { inicio_ms: 0, duracion_ms: 3500, ken_burns: "in" };
  assert.equal(zoomKenBurns(c, 0), 1);
  cerca(zoomKenBurns(c, 1000), 1 + 0.08 * 30 / 105, "in a 1 s");
  assert.equal(zoomKenBurns(c, 99999), 1.08);
  cerca(zoomKenBurns({ ...c, ken_burns: "out" }, 1000), 1.08 - 0.08 * 30 / 105, "out a 1 s");
  assert.equal(zoomKenBurns({ ...c, ken_burns: null }, 1000), 1);
});

test("zoomKenBurns en el instante congelado usa el cuadro N-1", () => {
  const clip = { id: "c1", inicio_ms: 0, duracion_ms: 3000, ken_burns: "in" };
  const doc = {
    pistas: [
      { id: "p_video", tipo: "video", clips: [clip] },
      { id: "p_voz", tipo: "audio", clips: [{ id: "a1", inicio_ms: 0, duracion_ms: 4000, material_id: 2 }] },
    ],
  };
  const r = principalEn(doc, 3500);
  cerca(zoomKenBurns(clip, r.capas[0].tZoom), 1 + 0.08 * 89 / 90, "n=90, cuadro 89 (N-1)");
});

test("capasEn: solo imagen/texto no principales, activas y visibles, en orden de pista", () => {
  assert.deepEqual(capasEn(DOC, 1000).map((c) => c.clip.id), ["t1"]);
  assert.deepEqual(capasEn(DOC, 3000), []);
  const oculto = structuredClone(DOC);
  oculto.pistas[1].oculta = true;
  assert.deepEqual(capasEn(oculto, 1000), []);
});

test("posicionCapa: caja del transform y animación deslizar de 60 px", () => {
  const t1 = DOC.pistas[1].clips[0];
  const quieto = posicionCapa(t1, 2000, 400, 200, "9:16");
  assert.deepEqual([quieto.x, quieto.y, quieto.w, quieto.h], [340, 226, 400, 200]);
  const entrando = posicionCapa(t1, 350, 400, 200, "9:16");
  cerca(entrando.y, 226 - 0.5 * 60, "a mitad de la entrada");
});

test("posicionCapa: con dos keyframes x/y van por tramos y el tamaño es el de t=0", () => {
  const clip = {
    inicio_ms: 1000, duracion_ms: 2000,
    transform: { x: 0.5, y: 0.5, escala: 1, rotacion: 0, opacidad: 0.5, ancla: "centro" },
    keyframes: [{ t_ms: 0, transform: { x: 0.25 } }, { t_ms: 1000, transform: { x: 0.75, escala: 2 } }],
  };
  const inicio = posicionCapa(clip, 1000, 100, 100, "1:1");
  assert.deepEqual([inicio.x, inicio.w, inicio.opacidad], [220, 100, 0.5]);
  const medio = posicionCapa(clip, 1500, 100, 100, "1:1");
  // caja del kf 2 con escala 2 ancla centro: 810 - 100 = 710; a mitad: (220 + 710) / 2
  cerca(medio.x, 465, "x a mitad");
  assert.equal(medio.w, 100);
  assert.equal(posicionCapa(clip, 9000, 100, 100, "1:1").x, 710);
});
