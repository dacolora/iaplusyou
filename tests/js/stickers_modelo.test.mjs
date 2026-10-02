// La pestaña «Stickers» y las plantillas para vender (capa 5c, Tarea 8): lo
// puro de stickers_modelo.js — los 40 emojis de la spec D12.2, los nombres de
// los 20 stickers, qué secciones se ven según la fuente de emojis y las seis
// plantillas de «Texto».
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  EMOJIS, NOMBRES_STICKER, plantillasTexto, seccionesStickers, TITULOS,
} from "../../static/editor/stickers_modelo.js";
import { ES, ponerTextos } from "../../static/editor/textos.js";
import { PRESETS_TEXTO } from "../../static/editor/operaciones.js";

const leer = (ruta) => JSON.parse(readFileSync(new URL(ruta, import.meta.url), "utf8"));
const TABLA = leer("../../static/editor/tipografia.json");
const MANIFIESTO = leer("../../static/stickers/stickers.json").stickers;
const T0 = { ...TABLA, emoji: null };
// una fuente de emojis de mentira que solo trae 🔥 👍 👨 y ❤ (👨 no está en la lista de la spec)
const T_E = { ...T0, emoji: { id: "E", upem: 1000, asc: 900, desc: 200,
  avances: [[0x2764, [1000]], [0x1F44D, [1000]], [0x1F468, [1000]], [0x1F525, [1000]]] } };

const ficha = (id, categoria, color = "#FFD400") => ({ id, categoria, archivo: `${id}.png`, ancho: 512, alto: 400, color,
  url: `/static/stickers/${id}.png?v=1` });
const TRES = [ficha("flecha_recta", "flechas"), ficha("circulo_mano", "marcas", "#E11D48"), ficha("estrella", "formas")];

test("EMOJIS: los 40 de la spec D12.2, en ese orden, cada uno un solo carácter y sin selectores", () => {
  // la lista de la spec, copiada tal cual (docs/superpowers/specs/2026-10-01-editor-capa5c-textos-graficos-design.md)
  const spec = "🔥 ✅ ⭐ 💯 🎁 🚚 💥 ❤ 👇 👉 😍 🤩 🛒 💸 ⏰ 🆕 ✨ 📦 💪 🙌 👀 ‼ ⚡ 🎉 🥇 👍 😱 🤑 📣 🔔 ⬇ ➡ ✔ ❌ 🌟 💎 🎯 🧡 🏷 🛍".split(" ");
  assert.equal(spec.length, 40);
  assert.deepEqual([...EMOJIS], spec);
  for (const e of EMOJIS) {
    assert.equal(typeof e, "string");
    assert.equal(Array.from(e).length, 1, `${e} es un solo carácter (sin selector de variación)`);
  }
  assert.equal(new Set(EMOJIS).size, 40);
  assert.equal(EMOJIS.includes("❤️"), false);
  assert.equal(EMOJIS[7], "❤", "«❤» es U+2764 solo");
});

test("NOMBRES_STICKER: los 20 stickers del manifiesto del repo, cada uno con su clave bib.sticker_<id> escrita entera", () => {
  assert.equal(MANIFIESTO.length, 20);
  assert.deepEqual(Object.keys(NOMBRES_STICKER).sort(), MANIFIESTO.map((s) => s.id).sort());
  for (const [id, clave] of Object.entries(NOMBRES_STICKER)) {
    assert.equal(clave, `bib.sticker_${id}`);
    assert.ok(ES[clave] && ES[clave].length > 2, `${clave} tiene su texto`);
  }
  assert.deepEqual(TITULOS, { flechas: "bib.flechas", marcas: "bib.marcas", formas: "bib.formas", emojis: "bib.emojis" });
  for (const clave of Object.values(TITULOS)) assert.ok(ES[clave], clave);
});

test("seccionesStickers: sin fuente de emojis, tres secciones (flechas, marcas, formas), sin la de emojis", () => {
  const secciones = seccionesStickers(TRES, T0);
  assert.deepEqual(secciones.map((s) => s.seccion), ["flechas", "marcas", "formas"]);
  assert.deepEqual(secciones.map((s) => s.titulo), ["Flechas", "Marcas a mano", "Formas"]);
  assert.deepEqual(secciones[0].items, [{ id: "flecha_recta", url: "/static/stickers/flecha_recta.png?v=1", color: "#FFD400", nombre: "Flecha" }]);
  assert.deepEqual(secciones[1].items, [{ id: "circulo_mano", url: "/static/stickers/circulo_mano.png?v=1", color: "#E11D48", nombre: "Círculo a mano" }]);
  assert.deepEqual(secciones[2].items.map((i) => i.nombre), ["Estrella"]);
  // sin tabla (o con una tabla sin la clave): igual, sin emojis y sin romper
  assert.deepEqual(seccionesStickers(TRES, null).map((s) => s.seccion), ["flechas", "marcas", "formas"]);
  assert.deepEqual(seccionesStickers(TRES, undefined).map((s) => s.seccion), ["flechas", "marcas", "formas"]);
  assert.deepEqual(seccionesStickers(TRES, { fuentes: TABLA.fuentes }).map((s) => s.seccion), ["flechas", "marcas", "formas"]);
});

test("seccionesStickers: con fuente de emojis, la cuarta sección trae solo los de la lista que la tabla cubre, en el orden de la lista", () => {
  const secciones = seccionesStickers(TRES, T_E);
  assert.deepEqual(secciones.map((s) => s.seccion), ["flechas", "marcas", "formas", "emojis"]);
  const emojis = secciones[3];
  assert.equal(emojis.titulo, "Emojis");
  assert.deepEqual(emojis.items, [{ emoji: "🔥" }, { emoji: "❤" }, { emoji: "👍" }]);   // 👨 está en la fuente pero no en la lista
  // la tabla trae el emoji pero no uno de la lista: no sale
  const otra = { ...T0, emoji: { id: "E", upem: 1000, asc: 900, desc: 200, avances: [[0x1F468, [1000]]] } };
  assert.deepEqual(seccionesStickers(TRES, otra).map((s) => s.seccion), ["flechas", "marcas", "formas"]);
});

test("seccionesStickers: con la tabla real, un emoji que la fuente de texto ya trae (‼) no sale como emoji", () => {
  const emojis = seccionesStickers([], TABLA).find((s) => s.seccion === "emojis");
  assert.ok(emojis, "la tabla real trae la fuente de emojis");
  assert.equal(emojis.items.length, 39);
  assert.equal(emojis.items.some((i) => i.emoji === "‼"), false);
  assert.deepEqual(emojis.items.slice(0, 3).map((i) => i.emoji), ["🔥", "✅", "⭐"]);
  assert.deepEqual(emojis.items.map((i) => i.emoji), EMOJIS.filter((e) => e !== "‼"));
});

test("seccionesStickers: una sección vacía no sale; el orden dentro de cada una es el del manifiesto", () => {
  assert.deepEqual(seccionesStickers([], T0), []);
  assert.deepEqual(seccionesStickers([ficha("estrella", "formas")], T0).map((s) => s.seccion), ["formas"]);
  assert.deepEqual(seccionesStickers([ficha("rayo", "formas"), ficha("flecha_recta", "flechas"), ficha("corazon", "formas")], T0)
    .map((s) => [s.seccion, s.items.map((i) => i.id)]), [["flechas", ["flecha_recta"]], ["formas", ["rayo", "corazon"]]]);
  // una categoría que no se conoce no se muestra (la ruta tampoco la ofrece)
  assert.deepEqual(seccionesStickers([ficha("x", "otra")], T0), []);
  // el manifiesto real: 4 flechas, 6 marcas y 10 formas, y los 20 con su nombre
  const real = seccionesStickers(MANIFIESTO.map((s) => ({ ...s, url: `/static/stickers/${s.archivo}` })), T0);
  assert.deepEqual(real.map((s) => [s.seccion, s.items.length]), [["flechas", 4], ["marcas", 6], ["formas", 10]]);
  for (const s of real) for (const i of s.items) assert.equal(i.nombre, ES[NOMBRES_STICKER[i.id]]);
});

test("seccionesStickers: el nombre sale en el idioma de la página (t), y un sticker nuevo sin nombre se llama por su id", () => {
  ponerTextos({ "bib.sticker_estrella": "Star", "bib.formas": "Shapes" }, "en");
  try {
    const formas = seccionesStickers([ficha("estrella", "formas"), ficha("nuevo_raro", "formas")], T0)[0];
    assert.equal(formas.titulo, "Shapes");
    assert.deepEqual(formas.items.map((i) => i.nombre), ["Star", "nuevo_raro"]);
  } finally {
    ponerTextos({}, "es");
  }
});

test("seccionesStickers no se rompe con una fuente de emojis y sin la fuente de los emojis en la tabla", () => {
  const sinInter = { ...T_E, fuentes: {} };
  assert.deepEqual(seccionesStickers(TRES, sinInter).map((s) => s.seccion), ["flechas", "marcas", "formas"]);
  assert.deepEqual(seccionesStickers(null, T_E).map((s) => s.seccion), ["emojis"]);
});

test("plantillasTexto: las seis de la spec D12.1, «OFERTA» primero, cada una un preset que agregarTexto conoce", () => {
  const p = plantillasTexto();
  assert.deepEqual(p.map((x) => x.preset), ["oferta", "nuevo", "descuento", "envio", "ultimas", "mas_vendido"]);
  assert.deepEqual(p.map((x) => x.texto), ["OFERTA", "NUEVO", "-50 %", "ENVÍO GRATIS", "¡ÚLTIMAS UNIDADES!", "MÁS VENDIDO"]);
  for (const { preset } of p) assert.ok(Object.hasOwn(PRESETS_TEXTO, preset), preset);
  ponerTextos({ "op.plantilla_oferta": "SALE" }, "en");
  try {
    assert.equal(plantillasTexto()[0].texto, "SALE");
  } finally {
    ponerTextos({}, "es");
  }
});
