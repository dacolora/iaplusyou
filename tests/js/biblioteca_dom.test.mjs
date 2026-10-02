// La biblioteca del editor con un DOM de mentira (capa 5c, Tarea 8): cómo
// biblioteca.js arma la pestaña «Stickers» (cuadrículas, miniaturas sobre fondo
// oscuro, emojis y su atribución) y la sección «Para vender» de «Texto», y cómo
// un toque llega a agregar(). Corre en su propio proceso (node --test separa
// los archivos): el `document` de mentira no toca las demás pruebas.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// Un selector simple de los que biblioteca.js usa: `[data-x]`, `[data-x="v"]`, `tag[data-x]`, `[atributo="v"]`, `.clase`.
function coincide(n, selector) {
  const m = /^([a-z0-9]*)(?:\[([a-z-]+)(?:="([^"]*)")?\])?(?:\.([\w-]+))?$/i.exec(selector.trim());
  if (!m) return false;
  const [, tag, atributo, valor, clase] = m;
  if (tag && n.tagName !== tag.toUpperCase()) return false;
  if (clase && !n.classList.contains(clase)) return false;
  if (atributo) {
    const dato = atributo.startsWith("data-") ? n.dataset[atributo.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] : n.atributos[atributo];
    if (dato === undefined || dato === null) return false;
    if (valor !== undefined && String(dato) !== valor) return false;
  }
  return true;
}

class Nodo {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.hijos = [];
    this.padre = null;
    this.style = { setProperty() {}, removeProperty() {} };
    this.dataset = {};
    this.atributos = {};
    this.oyentes = {};
    this.hidden = false;
    this.className = "";
    this.propio = "";
    this.innerHTML = "";
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

  prepend(...xs) {
    for (const x of xs) x.padre = this;
    this.hijos.unshift(...xs);
  }

  replaceChildren(...xs) {
    this.hijos = [];
    this.propio = "";
    this.append(...xs);
  }

  remove() {
    if (this.padre) this.padre.hijos = this.padre.hijos.filter((h) => h !== this);
    this.padre = null;
  }

  setAttribute(k, v) { this.atributos[k] = String(v); }

  getAttribute(k) { return this.atributos[k] ?? null; }

  addEventListener(tipo, fn) { (this.oyentes[tipo] ??= []).push(fn); }

  removeEventListener() {}

  contains(n) {
    for (let x = n; x; x = x.padre) if (x === this) return true;
    return false;
  }

  closest(selectores) {
    const lista = selectores.split(",");
    for (let x = this; x; x = x.padre) if (lista.some((s) => coincide(x, s))) return x;
    return null;
  }

  todos() {
    return [this, ...this.hijos.filter((h) => typeof h !== "string").flatMap((h) => h.todos())];
  }

  querySelectorAll(selector) {
    return this.todos().slice(1).filter((n) => coincide(n, selector));
  }

  querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }
}

globalThis.document = { createElement: (tag) => new Nodo(tag), createElementNS: (_ns, tag) => new Nodo(tag), addEventListener() {}, removeEventListener() {} };
globalThis.window = { addEventListener() {}, removeEventListener() {}, innerWidth: 375, innerHeight: 800 };
globalThis.fetch = async () => ({
  ok: true, status: 200, redirected: false, headers: { get: () => "application/json" },
  json: async () => ({ materiales: [], piezas: [] }),
});
const { Biblioteca } = await import("../../static/editor/biblioteca.js");

const leer = (ruta) => JSON.parse(readFileSync(new URL(ruta, import.meta.url), "utf8"));
const TABLA = leer("../../static/editor/tipografia.json");
const T0 = { ...TABLA, emoji: null };
const MANIFIESTO = leer("../../static/stickers/stickers.json").stickers.map((s) => ({ ...s, url: `/static/stickers/${s.archivo}` }));
const T_E = { ...T0, emoji: { id: "E", upem: 1000, asc: 900, desc: 200, avances: [[0x2764, [1000]], [0x1F44D, [1000]], [0x1F525, [1000]]] } };

const NOMBRES_PESTANAS = { medios: "Medios", audio: "Audio", texto: "Texto", stickers: "Stickers", subtitulos: "Subtítulos", transiciones: "Transiciones" };

function pestanas(orden = Object.keys(NOMBRES_PESTANAS)) {
  const caja = new Nodo("div");
  orden.forEach((panel, i) => {
    const b = new Nodo("button");
    b.dataset.panel = panel;
    b.setAttribute("aria-selected", i === 0 ? "true" : "false");
    b.textContent = NOMBRES_PESTANAS[panel];
    caja.append(b);
  });
  return caja;
}

function editorFalso(llamadas = []) {
  return {
    doc: () => ({ pistas: [], marca: {} }), tiempo: () => 2500, seleccion: null, destino: () => "es_CO", info: () => ({}),
    escuchar: () => () => {}, agregarMateriales: () => {}, enConflicto: () => false, enfocarTexto: () => {},
    operar: (...a) => { llamadas.push(a); return true; },
  };
}

function biblioteca({ tabla = T_E, stickers = MANIFIESTO, orden } = {}) {
  const llamadas = [];
  const contenedor = new Nodo("div");
  const b = new Biblioteca({
    contenedor, pestanas: pestanas(orden), urls: { biblioteca: "/cliente/acme/ediciones/biblioteca" }, editor: editorFalso(llamadas),
    linea: { puntoEn: () => null, resaltar() {} }, stickers, tabla,
  });
  return { b, contenedor, llamadas, panel: (nombre) => contenedor.querySelector(`section[data-panel="${nombre}"]`) };
}

test("los paneles de la biblioteca: «Stickers» va entre «Texto» y «Subtítulos», con el título de su pestaña", () => {
  const { contenedor, panel } = biblioteca();
  assert.deepEqual(contenedor.querySelectorAll("section").map((s) => s.dataset.panel),
    ["medios", "audio", "texto", "stickers", "subtitulos", "transiciones"]);
  assert.equal(panel("stickers").querySelector(".ed-bib-cabeza").textContent, "Stickers");
});

test("la pestaña «Stickers»: una cuadrícula por sección (flechas, marcas, formas, emojis), cada una con su título", () => {
  const { panel } = biblioteca();
  const p = panel("stickers");
  const titulos = p.querySelectorAll(".ed-bib-titulo").map((n) => n.textContent);
  assert.deepEqual(titulos, ["Flechas", "Marcas a mano", "Formas", "Emojis"]);
  const cuadriculas = p.querySelectorAll(".ed-stickers-cuadricula");
  assert.deepEqual(cuadriculas.map((c) => c.dataset.seccion), ["flechas", "marcas", "formas", "emojis"]);
  assert.deepEqual(cuadriculas.map((c) => c.hijos.length), [4, 6, 10, 3]);
  // cada título va justo antes de su cuadrícula
  cuadriculas.forEach((c, i) => assert.equal(p.hijos[p.hijos.indexOf(c) - 1].textContent, titulos[i]));
});

test("cada sticker es un botón con su miniatura perezosa y su nombre traducido como aria-label y title", () => {
  const { panel, b } = biblioteca();
  const botones = panel("stickers").querySelectorAll("button.ed-sticker").filter((n) => !n.classList.contains("ed-sticker-emoji"));
  assert.equal(botones.length, 20);
  const estrella = botones.find((n) => n.dataset.clave === "s:estrella");
  assert.equal(estrella.tagName, "BUTTON");
  assert.equal(estrella.atributos.type ?? estrella.type, "button");
  assert.equal(estrella.getAttribute("aria-label"), "Estrella");
  assert.equal(estrella.title, "Estrella");
  const [img] = estrella.hijos;
  assert.equal(img.tagName, "IMG");
  assert.equal(img.loading, "lazy");
  assert.equal(img.src, "/static/stickers/estrella.png");
  assert.equal(img.alt, "", "la imagen es decoración: el nombre lo dice el botón");
  // los 20 con su nombre en español, ninguno vacío y ninguno repetido
  const nombres = botones.map((n) => n.getAttribute("aria-label"));
  assert.equal(new Set(nombres).size, 20);
  assert.ok(nombres.every((n) => n.length > 2));
  assert.deepEqual(nombres.slice(0, 4), ["Flecha", "Flecha curva", "Flecha a mano", "Flecha hacia abajo"]);
  // lo que cada botón agrega, anotado por su clave
  assert.deepEqual(b.cosas.get("s:estrella"), { tipo: "sticker", sticker: { id: "estrella", url: "/static/stickers/estrella.png", color: "#FFD400", nombre: "Estrella" }, nombre: "Estrella" });
  assert.ok(estrella.dataset.arrastrable !== undefined, "con el mouse también se arrastra a la línea de tiempo");
});

test("cada emoji es un botón con el emoji escrito; agrega un texto con ese emoji", () => {
  const { panel, b } = biblioteca();
  const emojis = panel("stickers").querySelectorAll("button.ed-sticker-emoji");
  assert.deepEqual(emojis.map((n) => n.textContent), ["🔥", "❤", "👍"]);
  assert.ok(emojis.every((n) => n.classList.contains("ed-sticker")));
  assert.deepEqual(emojis.map((n) => n.dataset.clave), ["e:🔥", "e:❤", "e:👍"]);
  assert.deepEqual(emojis.map((n) => n.getAttribute("aria-label")), ["🔥", "❤", "👍"]);
  assert.deepEqual(b.cosas.get("e:🔥"), { tipo: "texto", preset: "emoji", literal: "🔥", nombre: "🔥" });
});

test("la atribución de los emojis (licencia CC-BY de Twemoji) sale siempre que sale su sección, y solo entonces", () => {
  const con = biblioteca({ tabla: T_E });
  const pie = con.panel("stickers").querySelectorAll(".ed-stickers-atribucion");
  assert.deepEqual(pie.map((n) => n.textContent), ["Emojis: Twemoji (CC-BY 4.0)."]);
  const ultimo = con.panel("stickers").hijos.at(-1);
  assert.equal(ultimo, pie[0], "va al pie del panel, después de los emojis");
  // sin fuente de emojis: ni la sección ni la atribución
  const sin = biblioteca({ tabla: T0 });
  assert.deepEqual(sin.panel("stickers").querySelectorAll(".ed-bib-titulo").map((n) => n.textContent), ["Flechas", "Marcas a mano", "Formas"]);
  assert.deepEqual(sin.panel("stickers").querySelectorAll(".ed-stickers-atribucion"), []);
  assert.equal(sin.panel("stickers").textContent.includes("Twemoji"), false);
  // con la fuente pero ningún emoji de la lista que la tabla cubra: tampoco (no hay sección que atribuir)
  const vacia = biblioteca({ tabla: { ...T0, emoji: { id: "E", upem: 1000, asc: 900, desc: 200, avances: [[0x1F468, [1000]]] } } });
  assert.deepEqual(vacia.panel("stickers").querySelectorAll(".ed-stickers-atribucion"), []);
});

test("«Texto»: las cuatro muestras de siempre y, debajo, «Para vender» con sus seis plantillas, cada una con su estilo", () => {
  const { panel, b } = biblioteca();
  const p = panel("texto");
  const cuadriculas = p.querySelectorAll(".ed-bib-textos");
  assert.equal(cuadriculas.length, 2);
  assert.deepEqual(cuadriculas[0].hijos.map((n) => n.dataset.clave), ["t:titulo", "t:subtitulo", "t:precio", "t:llamado"]);
  const titulo = p.querySelectorAll(".ed-bib-titulo");
  assert.deepEqual(titulo.map((n) => n.textContent), ["Para vender"]);
  assert.ok(p.hijos.indexOf(titulo[0]) > p.hijos.indexOf(cuadriculas[0]), "debajo de las muestras de hoy");
  assert.equal(p.hijos[p.hijos.indexOf(cuadriculas[1]) - 1], titulo[0]);
  const botones = cuadriculas[1].hijos;
  assert.deepEqual(botones.map((n) => n.dataset.clave), ["t:oferta", "t:nuevo", "t:descuento", "t:envio", "t:ultimas", "t:mas_vendido"]);
  assert.deepEqual(botones.map((n) => n.textContent), ["OFERTA", "NUEVO", "-50 %", "ENVÍO GRATIS", "¡ÚLTIMAS UNIDADES!", "MÁS VENDIDO"]);
  for (const n of botones) {
    const preset = n.dataset.clave.slice(2);
    assert.ok(n.classList.contains("ed-bib-texto") && n.classList.contains(`ed-bib-texto-${preset}`), preset);
    assert.equal(n.hijos[0].className, "ed-bib-texto-muestra", preset);
    assert.ok(n.dataset.arrastrable !== undefined, preset);
  }
  assert.equal(botones[0].getAttribute("aria-label"), "Agregar un texto «OFERTA»");
  assert.deepEqual(b.cosas.get("t:oferta"), { tipo: "texto", preset: "oferta", nombre: "OFERTA" });
});

test("tocar una miniatura (la imagen de adentro) o un emoji o una plantilla llega a agregar() con su clave", () => {
  const { b, panel } = biblioteca();
  const tocadas = [];
  b.agregar = (clave, ...resto) => { tocadas.push([clave, ...resto]); return true; };
  const estrella = panel("stickers").querySelector('button[data-clave="s:estrella"]');
  b._clic({ target: estrella.hijos[0] });                       // el toque cae en la <img>
  b._clic({ target: panel("stickers").querySelector('button[data-clave="e:🔥"]') });
  b._clic({ target: panel("texto").querySelector('button[data-clave="t:oferta"]').hijos[0] });
  assert.deepEqual(tocadas, [["s:estrella"], ["e:🔥"], ["t:oferta"]]);
});

test("las listas de Medios se repintan sin tocar las cosas de Stickers, emojis y plantillas", () => {
  const { b } = biblioteca();
  b._pintarListas();
  for (const clave of ["s:estrella", "e:🔥", "t:oferta", "t:titulo"]) assert.ok(b.cosas.has(clave), clave);
});
