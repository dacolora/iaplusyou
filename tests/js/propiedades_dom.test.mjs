// El panel «Editar» de un texto (capa 5c, Tarea 7) con un DOM de mentira:
// cómo propiedades.js engancha lo que propiedades_modelo.js decide — el
// deslizador «Ancho del texto» (un deshacer por arrastre), «Sin límite», la
// lista de fuentes por familia (cada nombre en su letra, y las fuentes se
// piden una vez) y el botón «Mostrar los emojis» de un texto de antes.
// Corre en su propio proceso (node --test separa los archivos): el
// `document` de mentira no toca las demás pruebas.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as op from "../../static/editor/operaciones.js";
import { docBase } from "./doc_base.mjs";

class Nodo {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.hijos = [];
    this.padre = null;
    this.style = {};
    this.dataset = {};
    this.atributos = {};
    this.oyentes = {};
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.value = "";
    this.className = "";
    this.id = "";
    this.propio = "";
  }

  get textContent() {
    return this.propio + this.hijos.map((h) => (typeof h === "string" ? h : h.textContent)).join("");
  }

  set textContent(v) {
    this.propio = String(v);
    this.hijos = [];
  }

  get classList() {
    const clases = () => this.className.split(/\s+/).filter(Boolean);
    return {
      add: (...cs) => { this.className = [...new Set([...clases(), ...cs])].join(" "); },
      toggle: (c, si) => {
        const quedan = clases().filter((x) => x !== c);
        this.className = (si ? [...quedan, c] : quedan).join(" ");
      },
      contains: (c) => clases().includes(c),
    };
  }

  append(...xs) {
    for (const x of xs) {
      if (typeof x !== "string") x.padre = this;
      this.hijos.push(x);
    }
  }

  replaceChildren(...xs) {
    this.hijos = [];
    this.propio = "";
    this.append(...xs);
  }

  setAttribute(k, v) { this.atributos[k] = String(v); }

  getAttribute(k) { return this.atributos[k] ?? null; }

  addEventListener(tipo, fn) { (this.oyentes[tipo] ??= []).push(fn); }

  disparar(tipo) {
    for (const fn of this.oyentes[tipo] ?? []) fn({ target: this, detail: 0 });
  }

  contains(n) {
    for (let x = n; x; x = x.padre) if (x === this) return true;
    return false;
  }

  closest() { return null; }

  querySelector() { return null; }

  todos() {
    return [this, ...this.hijos.filter((h) => typeof h !== "string").flatMap((h) => h.todos())];
  }
}

globalThis.document = { createElement: (tag) => new Nodo(tag), activeElement: null };
const { Propiedades } = await import("../../static/editor/propiedades.js");

const INFO = { 1: { duracion_ms: 8000, tiene_audio: true }, 2: { duracion_ms: 3000 } };
const TABLA = JSON.parse(readFileSync(new URL("../../static/editor/tipografia.json", import.meta.url), "utf8"));
const T_E = { ...TABLA, emoji: { id: "E", upem: 1000, asc: 900, desc: 200, avances: [[0x1F525, [1000]]] } };
const CATALOGO_4 = [
  { id: "Inter-Bold", nombre: "Inter Bold", categoria: "clasicas" },
  { id: "DMSerifDisplay-Regular", nombre: "DM Serif Display", categoria: "serifa" },
  { id: "Anton-Regular", nombre: "Anton", categoria: "impacto" },
  { id: "SpaceGrotesk-Bold", nombre: "Space Grotesk", categoria: "clasicas" },
];

// Un `editor` (pagina_editor.js) que anota lo que se le pide y nunca rechaza.
// `cargarFuentes` devuelve una promesa por pedido que la prueba cumple a mano
// (`bajada[id](resultado)`: [true] bajó, [false] no), como vista.cargarFuentes.
function editorFalso(doc, seleccion) {
  const llamadas = [];
  const pedidas = [];
  const bajada = {};
  const editor = {
    doc: () => editor.actual,
    actual: doc,
    seleccion,
    destino: () => "es_CO",
    info: () => INFO,
    enConflicto: () => false,
    operar: (...a) => { llamadas.push(["operar", ...a]); return true; },
    operarCon: (o, ...a) => { llamadas.push(["operarCon", o, ...a]); return true; },
    escuchar: () => () => {},
    cargarFuentes: (ids) => {
      pedidas.push(ids);
      return new Promise((cumplir) => { for (const id of ids) bajada[id] = cumplir; });
    },
  };
  return { editor, llamadas, pedidas, bajada };
}

// Un IntersectionObserver de mentira: la prueba decide cuándo «se ve» lo observado.
const vigias = [];
class VigiaFalso {
  constructor(alVer) {
    this.alVer = alVer;
    this.nodos = [];
    this.desconectado = false;
    vigias.push(this);
  }

  observe(nodo) { this.nodos.push(nodo); }

  disconnect() { this.desconectado = true; }

  ver(si = true) { this.alVer(this.nodos.map((target) => ({ target, isIntersecting: si })), this); }
}
const conVigia = () => { vigias.length = 0; globalThis.IntersectionObserver = VigiaFalso; };
const sinVigia = () => { vigias.length = 0; delete globalThis.IntersectionObserver; };
const vuelta = () => new Promise((r) => setImmediate(r));

function panel(doc, seleccion) {
  const falso = editorFalso(doc, seleccion);
  const contenedor = new Nodo("div");
  const p = new Propiedades({ contenedor, editor: falso.editor, catalogoFuentes: CATALOGO_4, tabla: T_E });
  const buscar = (fn) => contenedor.todos().filter(fn);
  return { p, contenedor, buscar, porId: (id) => buscar((n) => n.id === id)[0], ...falso };
}

function textoViejoConEmoji() {
  const d = docBase();
  d.pistas[1].clips[0].texto = { literal: "Hola 🔥" };
  return d;
}

test("la lista de fuentes va por familia, con su nombre y su aria-label; elegir una la cambia", () => {
  sinVigia();
  const { buscar, llamadas } = panel(textoViejoConEmoji(), "t1");
  const familias = buscar((n) => n.classList.contains("ed-fuentes-familia"));
  assert.deepEqual(familias.map((n) => n.textContent), ["Clásicas", "De impacto", "Con serifa"]);
  const radios = buscar((n) => n.tagName === "INPUT" && n.type === "radio" && n.name === "ed-prop-fuente");
  assert.deepEqual(radios.map((r) => r.value), ["Inter-Bold", "SpaceGrotesk-Bold", "Anton-Regular", "DMSerifDisplay-Regular"]);
  assert.deepEqual(radios.filter((r) => r.checked).map((r) => r.value), ["Inter-Bold"]);
  const anton = radios.find((r) => r.value === "Anton-Regular");
  assert.equal(anton.getAttribute("aria-label"), "Anton");
  assert.equal(anton.padre.hijos[1].textContent, "Anton");
  anton.checked = true;
  anton.disparar("change");
  assert.deepEqual(llamadas.at(-1), ["operar", "cambiar", "t1", { estilo: { fuente: "Anton-Regular" } }]);
});

// D9.3: armar «Editar» no baja nada (en el celular la hoja está cerrada, pero
// maquetada: un span con `fontFamily` de una @font-face declarada ya la baja).
// Las fuentes se piden la primera vez que la lista SE VE, una vez por panel, y
// cada nombre se escribe en su letra recién cuando la suya bajó.
test("las fuentes de la lista se piden recién cuando la lista se ve, una vez, y cada nombre toma su letra al bajar", async () => {
  conVigia();
  try {
    const { p, editor, buscar, pedidas, bajada } = panel(textoViejoConEmoji(), "t1");
    const spans = () => buscar((n) => n.tagName === "SPAN" && n.padre?.hijos[0]?.name === "ed-prop-fuente");
    const letra = (id) => spans().find((n) => n.padre.hijos[0].value === id).style.fontFamily;
    assert.deepEqual(pedidas, [], "armar el formulario no baja nada");
    assert.ok(spans().every((n) => n.style.fontFamily === undefined), "ningún nombre pide su fuente antes de verse");
    assert.equal(vigias.length, 1);
    assert.ok(vigias[0].nodos[0].classList.contains("ed-fuentes"), "se vigila la lista de fuentes");
    vigias[0].ver(false);                                   // el aviso inicial de «no se ve»
    assert.deepEqual(pedidas, []);
    // otro texto y de vuelta, sin que la lista se haya visto: tampoco baja nada
    editor.seleccion = null;
    p.pintar();
    editor.seleccion = "t1";
    p.pintar();
    assert.deepEqual(pedidas, []);
    assert.equal(vigias[0].desconectado, true, "el vigía de la lista que se fue se suelta");
    const vigia = vigias.at(-1);
    vigia.ver(true);
    assert.deepEqual(pedidas.flat(), ["Inter-Bold", "SpaceGrotesk-Bold", "Anton-Regular", "DMSerifDisplay-Regular"]);
    assert.equal(vigia.desconectado, true);
    vigia.ver(true);                                        // otro aviso: nada nuevo
    assert.equal(pedidas.flat().length, 4);
    // nadie tiene su letra hasta que la suya baja
    assert.ok(spans().every((n) => n.style.fontFamily === undefined));
    bajada["Anton-Regular"]([true]);
    bajada["SpaceGrotesk-Bold"]([false]);                   // no bajó: su nombre queda en la letra de la página
    await vuelta();
    assert.match(letra("Anton-Regular"), /^"Anton-Regular"/);
    assert.equal(letra("SpaceGrotesk-Bold"), undefined);
    assert.equal(letra("Inter-Bold"), undefined);
    // la lista armada de nuevo: lo que ya bajó sale en su letra al momento; nada se vuelve a pedir ni a vigilar
    const vigiasAntes = vigias.length;
    editor.seleccion = null;
    p.pintar();
    editor.seleccion = "t1";
    p.pintar();
    assert.match(letra("Anton-Regular"), /^"Anton-Regular"/);
    assert.equal(letra("DMSerifDisplay-Regular"), undefined);
    assert.equal(vigias.length, vigiasAntes);
    bajada["DMSerifDisplay-Regular"]([true]);               // la que llega después le da su letra a la lista de ahora
    await vuelta();
    assert.match(letra("DMSerifDisplay-Regular"), /^"DMSerifDisplay-Regular"/);
    assert.equal(pedidas.flat().length, 4);
  } finally {
    sinVigia();
  }
});

test("sin IntersectionObserver, la lista pide sus fuentes al tocarla o al recibir el foco (una vez)", () => {
  sinVigia();
  const { buscar, pedidas } = panel(textoViejoConEmoji(), "t1");
  const lista = buscar((n) => n.classList.contains("ed-fuentes"))[0];
  assert.deepEqual(pedidas, []);
  lista.disparar("pointerdown");
  assert.deepEqual(pedidas.flat(), ["Inter-Bold", "SpaceGrotesk-Bold", "Anton-Regular", "DMSerifDisplay-Regular"]);
  lista.disparar("focusin");
  lista.disparar("pointerdown");
  assert.equal(pedidas.flat().length, 4);
  const otra = panel(textoViejoConEmoji(), "t1");
  otra.buscar((n) => n.classList.contains("ed-fuentes"))[0].disparar("focusin");
  assert.equal(otra.pedidas.flat().length, 4, "el foco también la abre");
});

test("«Ancho del texto»: un arrastre es un deshacer (clave <id>:ancho); «Sin límite» lo apaga", () => {
  const titulo = op.agregarTexto(docBase(), 0, "titulo", {}, INFO);
  const { editor, porId, llamadas, p } = panel(titulo.doc, titulo.seleccion);
  const id = titulo.seleccion;
  const deslizador = porId("ed-prop-ancho");
  const casilla = porId("ed-prop-sin-limite");
  assert.deepEqual([deslizador.type, deslizador.min, deslizador.max, deslizador.value, deslizador.disabled], ["range", "30", "100", "86", false]);
  assert.deepEqual([casilla.type, casilla.checked], ["checkbox", false]);
  deslizador.value = "50";
  deslizador.disparar("input");
  deslizador.value = "45";
  deslizador.disparar("input");
  assert.deepEqual(llamadas, [
    ["operarCon", { clave: `${id}:ancho` }, "cambiar", id, { estilo: { ancho_max: 0.5 } }],
    ["operarCon", { clave: `${id}:ancho` }, "cambiar", id, { estilo: { ancho_max: 0.45 } }],
  ]);
  casilla.checked = true;
  casilla.disparar("change");
  assert.deepEqual(llamadas.at(-1), ["operar", "cambiar", id, { estilo: { ancho_max: null } }]);
  // con «Sin límite» el deslizador queda quieto (y vuelve con la casilla)
  editor.actual = op.cambiar(titulo.doc, id, { estilo: { ancho_max: null } }, INFO).doc;
  p.pintar();
  assert.deepEqual([deslizador.disabled, casilla.checked], [true, true]);
  casilla.checked = false;
  casilla.disparar("change");
  assert.deepEqual(llamadas.at(-1), ["operar", "cambiar", id, { estilo: { ancho_max: 0.86 } }]);
  // el deslizador y la casilla van en una fila que se envuelve
  assert.equal(deslizador.padre, casilla.padre.padre);
  assert.ok(deslizador.padre.classList.contains("ed-prop-ancho-fila"));
});

test("un texto de antes con emojis: el aviso y «Mostrar los emojis» (una operación); ya nuevo, el aviso se va", () => {
  const { editor, buscar, llamadas, p, porId } = panel(textoViejoConEmoji(), "t1");
  const avisos = () => buscar((n) => n.classList.contains("ed-prop-aviso") && !n.hidden && n.textContent);
  assert.deepEqual(avisos().map((n) => n.textContent), ["Este texto es de antes: sus emojis no salen en el video."]);
  const boton = porId("ed-prop-mostrar-emojis");
  assert.equal(boton.textContent, "Mostrar los emojis");
  boton.disparar("click");
  assert.deepEqual(llamadas, [["operar", "actualizarTexto", "t1"]]);
  editor.actual = op.actualizarTexto(textoViejoConEmoji(), "t1", INFO).doc;
  p.pintar();
  assert.deepEqual(avisos(), []);
  assert.equal(porId("ed-prop-mostrar-emojis"), undefined);
  // un v2 con algo que la fuente no trae: el aviso, sin botón
  editor.actual = op.editarTexto(editor.actual, "t1", "Hola 🍕", "es_CO", INFO).doc;
  p.pintar();
  assert.deepEqual(avisos().map((n) => n.textContent), ["No sale en el video: «🍕» (esta fuente no los tiene)."]);
  assert.equal(porId("ed-prop-mostrar-emojis"), undefined);
});
