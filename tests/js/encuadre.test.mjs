// Paridad con final_edition/encuadre.py (D4-D7): tabla generada por Python
// (tests/fixtures/encuadre_casos.json) + los casos propios de `limpio`
// (solo navegador: no tiene espejo en Python).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { ajusteAutomatico, caja, completo, DEFECTO, esDefecto, fondo, limpio, par, rectConZoom }
  from "../../static/editor/encuadre.js";
import { FORMATOS } from "../../static/editor/formatos.js";

const CASOS = JSON.parse(readFileSync(new URL("../fixtures/encuadre_casos.json", import.meta.url), "utf8"));
const formatoLienzo = (formato) => FORMATOS[formato];

test("caja da los mismos enteros que encuadre.caja en cada caso de la tabla", () => {
  assert.ok(CASOS.cajas.length > 0);
  for (const c of CASOS.cajas) {
    assert.deepEqual(caja(c.ancho, c.alto, ...formatoLienzo(c.formato), c.encuadre), c.esperado,
      `${c.formato} ${c.ancho}x${c.alto} ${JSON.stringify(c.encuadre)}`);
  }
});

test("fondo da el mismo lienzo chico que encuadre.fondo en cada formato", () => {
  for (const [formato, esperado] of Object.entries(CASOS.fondos)) {
    assert.deepEqual(fondo(...formatoLienzo(formato)), esperado, formato);
  }
});

test("ajusteAutomatico da lo mismo que encuadre.ajuste_automatico en cada caso de la tabla", () => {
  assert.ok(CASOS.automaticos.length > 0);
  for (const c of CASOS.automaticos) {
    assert.deepEqual(ajusteAutomatico(c.ancho, c.alto, ...formatoLienzo(c.formato)), c.esperado,
      `${c.formato} ${c.ancho}x${c.alto}`);
  }
});

test("caja nunca devuelve -0 (el caso centrado 1080x1920)", () => {
  const c = caja(1920, 1080, 1080, 1920, null);
  assert.equal(Object.is(c.px, -0), false);
  assert.equal(Object.is(c.py, -0), false);
});

test("par: los mismos casos que Python", () => {
  assert.equal(par(1166.5), 1166);
  assert.equal(par(1167), 1168);
  assert.equal(par(-690), -690);
  assert.equal(par(607.5), 608);
});

test("completo rellena con el defecto", () => {
  assert.deepEqual(completo(null), DEFECTO);
  assert.deepEqual(completo({}), DEFECTO);
  assert.deepEqual(completo({ modo: "ajustar" }), { modo: "ajustar", zoom: 1.0, x: 0.5, y: 0.5 });
});

test("esDefecto: ausente, null y el objeto completo por defecto son el defecto", () => {
  assert.equal(esDefecto(undefined), true);
  assert.equal(esDefecto(null), true);
  assert.equal(esDefecto({}), true);
  assert.equal(esDefecto({ modo: "llenar", zoom: 1.0, x: 0.5, y: 0.5 }), true);
  assert.equal(esDefecto({ modo: "ajustar" }), false);
  assert.equal(esDefecto({ zoom: 1.5 }), false);
});

test("limpio: acota zoom a 1-4 y x/y a 0-1", () => {
  assert.deepEqual(limpio({ zoom: 9, x: -1 }), { modo: "llenar", zoom: 4, x: 0, y: 0.5 });
});

test("limpio: el defecto completo da null", () => {
  assert.equal(limpio({ modo: "llenar", zoom: 1, x: 0.5, y: 0.5 }), null);
  assert.equal(limpio(null), null);
});

test("limpio: redondea a 4 decimales", () => {
  assert.equal(limpio({ x: 0.123456 }).x, 0.1235);
});

test("limpio: un modo fuera de MODOS pasa tal cual (no valida, solo limpia los números)", () => {
  assert.deepEqual(limpio({ modo: "estirar" }), { modo: "estirar", zoom: 1, x: 0.5, y: 0.5 });
});

// ---- rectConZoom (solo navegador, Tarea 4): el zoom lento acerca hacia el
// centro del lienzo (como zoompan); dx desplaza (transición «deslizar») ----

test("rectConZoom: zoom lento 1,04 acerca hacia el centro del lienzo (±1e-9)", () => {
  const r = rectConZoom({ x: 0, y: 0, w: 3840, h: 1920 }, 1.04, 0, 1080, 1920);
  assert.ok(Math.abs(r.x - -21.6) < 1e-9, r.x);
  assert.ok(Math.abs(r.y - -38.4) < 1e-9, r.y);
  assert.ok(Math.abs(r.w - 3993.6) < 1e-9, r.w);
  assert.ok(Math.abs(r.h - 1996.8) < 1e-9, r.h);
});

test("rectConZoom: zoom 1 y dx 0 devuelve el mismo rectángulo", () => {
  const rect = { x: 10, y: 20, w: 300, h: 400 };
  assert.deepEqual(rectConZoom(rect, 1, 0, 1080, 1920), rect);
});

test("rectConZoom: dx desplaza en fracción del ancho del lienzo (deslizar)", () => {
  const r = rectConZoom({ x: 0, y: 0, w: 3840, h: 1920 }, 1, -0.5, 1080, 1920);
  assert.equal(r.x, -540);
});

// ---- Tarea 7 (D8): mover y acercar el encuadre sobre el video, y la caja
// que se ve (la selección del clip de la principal) ----
import { cajaVisible, IMAN_ENCUADRE_PX, moverEncuadre, sinMargen, zoomEncuadre } from "../../static/editor/encuadre.js";

const SIN_GUIAS = { vertical: false, horizontal: false };

test("moverEncuadre: la imagen sigue al dedo (400×200 en llenar: sw 3840, 2760 px de margen a lo ancho)", () => {
  assert.equal(caja(400, 200, 1080, 1920, null).sw, 3840);
  assert.deepEqual(moverEncuadre(null, [400, 200], 1080, 1920, 276, 0), { x: 0.4, y: 0.5, guias: SIN_GUIAS });
  // hacia la izquierda se ve más de la derecha del cuadro
  assert.deepEqual(moverEncuadre(null, [400, 200], 1080, 1920, -276, 0), { x: 0.6, y: 0.5, guias: SIN_GUIAS });
  // nunca pasa del borde del cuadro
  assert.deepEqual(moverEncuadre(null, [400, 200], 1080, 1920, -3000, 0), { x: 1, y: 0.5, guias: SIN_GUIAS });
  assert.deepEqual(moverEncuadre(null, [400, 200], 1080, 1920, 3000, 0), { x: 0, y: 0.5, guias: SIN_GUIAS });
  // desde donde estaba (no desde el centro)
  assert.deepEqual(moverEncuadre({ x: 0.4 }, [400, 200], 1080, 1920, 276, 0), { x: 0.3, y: 0.5, guias: SIN_GUIAS });
});

test("moverEncuadre: imán al centro a menos de `iman` px del lienzo (y lo dice en las guías)", () => {
  assert.deepEqual(moverEncuadre(null, [400, 200], 1080, 1920, 5, 0),
    { x: 0.5, y: 0.5, guias: { vertical: true, horizontal: false } });
  // a 13 px no pega con el imán de 12; con uno más grande, sí
  assert.equal(moverEncuadre(null, [400, 200], 1080, 1920, 13, 0).guias.vertical, false);
  assert.deepEqual(moverEncuadre(null, [400, 200], 1080, 1920, 30, 0, { iman: 40 }),
    { x: 0.5, y: 0.5, guias: { vertical: true, horizontal: false } });
  // desde un costado, llegar cerca del centro pega
  assert.deepEqual(moverEncuadre({ x: 0.4 }, [400, 200], 1080, 1920, -270, 0),
    { x: 0.5, y: 0.5, guias: { vertical: true, horizontal: false } });
});

test("moverEncuadre: sin margen en un eje (el cuadro mide lo mismo que el lienzo) ese eje no cambia ni pega", () => {
  // ajustar 400×200: sw = W (no se mueve a lo ancho), sh 540 < H (se mueve dentro del lienzo)
  assert.equal(caja(400, 200, 1080, 1920, { modo: "ajustar" }).sw, 1080);
  assert.deepEqual(moverEncuadre({ modo: "ajustar" }, [400, 200], 1080, 1920, 300, 138),
    { x: 0.5, y: 0.6, guias: SIN_GUIAS });
  assert.deepEqual(moverEncuadre({ modo: "ajustar", x: 0.2 }, [400, 200], 1080, 1920, 300, 0),
    { x: 0.2, y: 0.5, guias: { vertical: false, horizontal: true } });
  // llenar con la misma proporción que el lienzo y sin acercar: nada se mueve
  assert.deepEqual(moverEncuadre(null, [1080, 1920], 1080, 1920, 100, 100), { x: 0.5, y: 0.5, guias: SIN_GUIAS });
});

test("moverEncuadre: a 4 decimales", () => {
  const r = moverEncuadre(null, [400, 200], 1080, 1920, 100, 0);
  assert.equal(r.x, Math.round((0.5 - 100 / 2760) * 10000) / 10000);
});

test("zoomEncuadre: la distancia al centro del lienzo manda (asa en 1072, 1912)", () => {
  const asa = { x: 1072, y: 1912 };
  assert.equal(zoomEncuadre(null, asa, 532, 952, 1080, 1920), 2);
  assert.equal(zoomEncuadre({ zoom: 1.5 }, asa, 532, 952, 1080, 1920), 3);
  assert.equal(zoomEncuadre(null, asa, 5000, 5000, 1080, 1920), 4);            // muy afuera: el tope
  assert.equal(zoomEncuadre({ zoom: 3 }, asa, -266, -476, 1080, 1920), 1.5);    // a mitad de camino del centro
  assert.equal(zoomEncuadre({ zoom: 2 }, asa, -532, -952, 1080, 1920), 1);     // hasta el centro: el mínimo
  // pasar del centro no lo vuelve a agrandar (la distancia volvería a crecer)
  assert.equal(zoomEncuadre({ zoom: 2 }, asa, -2000, -3000, 1080, 1920), 1);
  assert.equal(zoomEncuadre({ zoom: 2.5 }, asa, 0, 0, 1080, 1920), 2.5);        // sin moverse, igual
  const r = zoomEncuadre(null, asa, 100, 0, 1080, 1920);
  assert.equal(r, Math.round(Math.hypot(632, 952) / Math.hypot(532, 952) * 10000) / 10000);
});

test("cajaVisible: el cuadro colocado, recortado al lienzo", () => {
  assert.deepEqual(cajaVisible(null, [400, 200], 1080, 1920), { x: 0, y: 0, ancho: 1080, alto: 1920 });
  assert.deepEqual(cajaVisible({ x: 0, zoom: 2 }, [400, 200], 1080, 1920), { x: 0, y: 0, ancho: 1080, alto: 1920 });
  assert.deepEqual(cajaVisible({ modo: "ajustar" }, [400, 200], 1080, 1920), { x: 0, y: 690, ancho: 1080, alto: 540 });
  assert.deepEqual(cajaVisible({ modo: "ajustar", y: 1 }, [400, 200], 1080, 1920), { x: 0, y: 1380, ancho: 1080, alto: 540 });
  // ajustar acercado: pasa del lienzo a lo ancho (se recorta) y queda centrado a lo alto
  assert.deepEqual(cajaVisible({ modo: "ajustar", zoom: 2 }, [400, 200], 1080, 1920), { x: 0, y: 420, ancho: 1080, alto: 1080 });
  // sin medidas no se sabe dónde queda: el lienzo entero
  assert.deepEqual(cajaVisible({ modo: "ajustar" }, null, 1080, 1920), { x: 0, y: 0, ancho: 1080, alto: 1920 });
});

// Revisión final de la capa 5b: un margen más chico que el imán (1080×1918
// en 9:16 llena con sw 1082: 2 px a lo ancho) nunca se movía — todo arrastre
// terminaba pegado al centro —, y el panel no decía «sin margen».
test("moverEncuadre: un eje con menos margen que el imán no se mueve ni marca guía", () => {
  assert.equal(caja(1080, 1918, 1080, 1920, null).sw, 1082);
  assert.ok(sinMargen(null, [1080, 1918], 1080, 1920));
  assert.deepEqual(moverEncuadre(null, [1080, 1918], 1080, 1920, 100, 0), { x: 0.5, y: 0.5, guias: SIN_GUIAS });
  assert.ok(!sinMargen(null, [400, 200], 1080, 1920));
  assert.ok(!sinMargen({ zoom: 1.5 }, [1080, 1918], 1080, 1920));
  assert.equal(IMAN_ENCUADRE_PX, 12);
});

test("moverEncuadre: un margen chico (30 px) con un imán grande (24) igual llega al borde — el imán nunca lo atrapa", () => {
  assert.equal(caja(1110, 1920, 1080, 1920, null).sw, 1110);
  assert.deepEqual(moverEncuadre(null, [1110, 1920], 1080, 1920, -100, 0, { iman: 24 }), { x: 1, y: 0.5, guias: SIN_GUIAS });
  assert.deepEqual(moverEncuadre(null, [1110, 1920], 1080, 1920, 100, 0, { iman: 24 }), { x: 0, y: 0.5, guias: SIN_GUIAS });
  // cerca del centro sigue pegando (un cuarto del margen: 7,5 px)
  assert.deepEqual(moverEncuadre(null, [1110, 1920], 1080, 1920, 3, 0, { iman: 24 }),
    { x: 0.5, y: 0.5, guias: { vertical: true, horizontal: false } });
});
