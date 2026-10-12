// «Resultados»: qué días de la gráfica abren «Qué pasó el …» y qué dice cuando no se puede (PND-294, 2026-10-12).
// Corre static/tw_resultados.js entero con un DOM de mentira (sin jsdom ni npm): un día `sin_dia` (la ruta del detalle lo
// rechazaría con un 400) no se pide ni con el clic, ni con las flechas + Enter, ni con «Ver qué pasó →», y su recuadro
// dice por qué en vez de invitar al clic; y un 400 con su motivo en palabras lo muestra la gráfica, como texto.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

class El {
  constructor(tag) {
    this.tagName = tag; this.children = []; this.attrs = {}; this._clases = new Set(); this.dataset = {};
    this.style = {}; this.handlers = {}; this._texto = ''; this.html = null; this.hidden = false; this.mapa = {};
    this.clientWidth = 720; this.offsetWidth = 200; this.isConnected = true;
  }
  get firstChild() { return this.children[0] || null; }
  appendChild(c) { this.children.push(c); return c; }
  removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  set className(v) { this._clases = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get className() { return [...this._clases].join(' '); }
  get classList() {
    const s = this._clases;
    return {
      add: (c) => s.add(c), remove: (c) => s.delete(c), contains: (c) => s.has(c),
      toggle: (c, forzar) => { const on = forzar === undefined ? !s.has(c) : !!forzar; if (on) s.add(c); else s.delete(c); return on; },
    };
  }
  set textContent(v) { this.children = []; this._texto = String(v); }
  get textContent() { return this._texto + this.children.map((c) => c.textContent).join(''); }
  set innerHTML(v) { this.children = []; this._texto = ''; this.html = String(v); }
  addEventListener(tipo, f) { (this.handlers[tipo] = this.handlers[tipo] || []).push(f); }
  disparar(tipo, ev) { (this.handlers[tipo] || []).forEach((f) => f(ev)); }
  getBoundingClientRect() { return { left: 0, top: 0, width: 720, height: 270 }; }
  scrollIntoView() {}
  querySelectorAll(sel) { return this.mapa[sel] || []; }
  querySelector(sel) { return (this.mapa[sel] || [])[0] || null; }
}

globalThis.window = globalThis;
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.document = {
  documentElement: { lang: 'es' },
  createElement: (tag) => new El(tag),
  createElementNS: (ns, tag) => new El(tag),
  createTextNode: (t) => { const n = new El('#text'); n.textContent = t; return n; },
  getElementById: () => null,
};
(0, eval)(fs.readFileSync(new URL('../../static/tw_resultados.js', import.meta.url), 'utf8'));
const P = window.TwResultados._puro;

// -------------------------------------------------------------------------------------------- lo puro ---

test('un día se abre salvo hoy, sin copia o sin_dia', () => {
  assert.equal(P.diaAbrible({ f: '2026-10-05' }, false), true);
  assert.equal(P.diaAbrible({ f: '2026-10-05' }, true), false);
  assert.equal(P.diaAbrible({ f: '2026-10-05', sin_copia: true }, false), false);
  assert.equal(P.diaAbrible({ f: '2026-10-05', sin_dia: true }, false), false);
  assert.equal(P.diaAbrible(undefined, false), false);
});

test('el motivo de un 400 es una frase corta de texto plano; lo demás no', () => {
  assert.equal(P.motivoCorto('  Ese día no tiene datos completos.\n'), 'Ese día no tiene datos completos.');
  assert.equal(P.motivoCorto(''), '');
  assert.equal(P.motivoCorto(undefined), '');
  assert.equal(P.motivoCorto('<!doctype html><title>400 Bad Request</title>'), '');
  assert.equal(P.motivoCorto('x'.repeat(201)), '');
  assert.equal(P.motivoCorto('x'.repeat(200)), 'x'.repeat(200));
});

// ------------------------------------------------------------------------ la gráfica con un DOM de mentira ---

// Diez días: del 1 al 4 `sin_dia` (la ruta los rechazaría), el 7 `sin_copia` y el 10 es hoy.
const FECHAS = Array.from({ length: 10 }, (_, i) => `2026-10-${String(i + 1).padStart(2, '0')}`);
const TEXTOS = { hoy: 'hoy', hoy_medias: 'hoy, a medias', pista: 'Clic para ver qué pasó ese día', antes: '%(dia)s (antes)',
                 sobre: '', bajo: '', nuevos: 'A anuncios nuevos', ventas: 'Ventas', gasto: 'Gasto', retorno: 'Retorno',
                 pedidos: 'Pedidos', nuevos_leyenda: '', viejos_leyenda: '', desconocida: '', previo: '', raro: '',
                 meta: '', promedio: '', grafica: 'Gráfica de %(m)s', cargando: 'Cargando…',
                 error_dia: 'No se pudo cargar ese día.', sin_copia: 'sin copia', sin_dia: 'todavía no estaban todas tus fuentes' };

function montar(cambios = {}) {
  const dias = FECHAS.map((f, i) => {
    if (i === 6) return { f, ing: null, gas: null, ped: null, nc: null, nue: null, sin_copia: true };
    const fila = { f, ing: 100 + i, gas: 50, ped: 2, nc: 0, nue: null };
    if (i < 4) fila.sin_dia = true;
    return fila;
  });
  const datos = { lang: 'es', moneda: 'USD', fuente: 'mixta', comparar: false, meta_roas: null, conocido_desde: null,
                  dia_inicial: '2026-10-09', url_dia: '/x/dia?entrada=', dias, previos: [], raros: {}, mejor: {},
                  metricas: [{ clave: 'ventas', etiqueta: 'Ventas', bueno: 1, formato: 'dinero' }], canales: [],
                  textos: TEXTOS, ...cambios };
  const el = (tag) => new El(tag);
  const seccion = el('section'), lienzo = el('svg'), aviso = el('div'), leyenda = el('ul'), caja = el('div'),
        detalle = el('div'), fuente = el('script'), raiz = el('div');
  fuente.textContent = JSON.stringify(datos);
  aviso.hidden = true;
  seccion.mapa = { '[data-twr-svg]': [lienzo], '[data-twr-aviso]': [aviso], '[data-twr-leyenda]': [leyenda],
                   '[data-twr-grafico]': [caja], '.twr-dia[data-twr-dia]': [detalle] };
  raiz.mapa = { '[data-twr]': [seccion], '#tw-resultados-datos': [fuente] };
  return { seccion, lienzo, aviso, detalle, raiz, datos };
}

// Las respuestas del servidor que va a recibir el fetch, y las URLs que se pidieron.
let pedidas = [], respuesta = null;
globalThis.fetch = (url) => {
  pedidas.push(url);
  return respuesta instanceof Error ? Promise.reject(respuesta) : Promise.resolve(respuesta);
};
const resp = (estado, cuerpo) => ({ ok: estado >= 200 && estado < 300, status: estado, text: () => Promise.resolve(cuerpo) });
const pasar = () => new Promise((r) => setTimeout(r, 0));

async function iniciar(r = resp(200, '<p>detalle</p>'), cambios = {}) {
  pedidas = []; respuesta = r;
  const g = montar(cambios);
  window.TwResultados.iniciar(g.raiz);
  await pasar();
  pedidas = [];                         // lo que pidió al nacer (el último día con datos) no es lo que se prueba
  return g;
}

// El x del centro del día `i` en el lienzo (720 de ancho, márgenes izq. 52 y der. 16).
const xDe = (i, n = FECHAS.length) => 52 + ((720 - 52 - 16) / n) * (i + 0.5);

test('al nacer pide el último día con datos', async () => {
  pedidas = []; respuesta = resp(200, '<p>x</p>');
  window.TwResultados.iniciar(montar().raiz);
  await pasar();
  assert.deepEqual(pedidas, ['/x/dia?entrada=&fecha=2026-10-09']);
});

test('el clic en un día sin_dia, sin copia u hoy no pide nada; en uno normal sí', async () => {
  const g = await iniciar();
  for (const i of [0, 3, 6, 9]) g.lienzo.disparar('click', { clientX: xDe(i) });
  await pasar();
  assert.deepEqual(pedidas, []);
  g.lienzo.disparar('click', { clientX: xDe(4) });
  await pasar();
  assert.deepEqual(pedidas, ['/x/dia?entrada=&fecha=2026-10-05']);
});

test('las flechas + Enter respetan la misma guarda', async () => {
  const g = await iniciar();
  const tecla = (key) => g.lienzo.disparar('keydown', { key, preventDefault() {} });
  tecla('Home'); tecla('Enter');                      // el 1 es sin_dia
  tecla('ArrowRight'); tecla('ArrowRight'); tecla('ArrowRight'); tecla('Enter');   // el 4 también
  await pasar();
  assert.deepEqual(pedidas, []);
  tecla('ArrowRight'); tecla('Enter');                // el 5 sí
  await pasar();
  assert.deepEqual(pedidas, ['/x/dia?entrada=&fecha=2026-10-05']);
});

test('«Ver qué pasó →» de un día sin_dia no pide nada', async () => {
  const g = await iniciar();
  const boton = (fecha) => ({ target: { closest: (sel) => (sel === 'button[data-twr-dia]' ? { getAttribute: () => fecha } : null) },
                              preventDefault() {} });
  g.seccion.disparar('click', boton('2026-10-02'));      // sin_dia
  g.seccion.disparar('click', boton('2026-10-07'));      // sin_copia
  g.seccion.disparar('click', boton('2026-10-10'));      // hoy
  await pasar();
  assert.deepEqual(pedidas, []);
  g.seccion.disparar('click', boton('2026-10-08'));
  await pasar();
  assert.deepEqual(pedidas, ['/x/dia?entrada=&fecha=2026-10-08']);
});

test('el recuadro de un día sin_dia dice por qué, no invita al clic y quita la mano', async () => {
  const g = await iniciar();
  g.lienzo.disparar('pointermove', { clientX: xDe(1) });
  assert.match(g.aviso.textContent, /todavía no estaban todas tus fuentes/);
  assert.doesNotMatch(g.aviso.textContent, /Clic para ver qué pasó/);
  assert.equal(g.lienzo.classList.contains('twr-sin-abrir'), true);
  g.lienzo.disparar('pointermove', { clientX: xDe(5) });
  assert.match(g.aviso.textContent, /Clic para ver qué pasó/);
  assert.doesNotMatch(g.aviso.textContent, /todavía no estaban/);
  assert.equal(g.lienzo.classList.contains('twr-sin-abrir'), false);
  g.lienzo.disparar('pointermove', { clientX: xDe(6) });           // sin copia: lo suyo, sin pista
  assert.match(g.aviso.textContent, /sin copia/);
  assert.doesNotMatch(g.aviso.textContent, /Clic para ver qué pasó/);
  g.lienzo.disparar('pointermove', { clientX: xDe(9) });           // hoy
  assert.match(g.aviso.textContent, /hoy, a medias/);
  assert.equal(g.lienzo.classList.contains('twr-sin-abrir'), true);
});

test('sin el texto sin_dia (una página vieja) el recuadro no escribe «undefined»', async () => {
  const g = montar();
  delete g.datos.textos.sin_dia;
  g.raiz.mapa['#tw-resultados-datos'][0].textContent = JSON.stringify(g.datos);
  respuesta = resp(200, '');
  window.TwResultados.iniciar(g.raiz);
  g.lienzo.disparar('pointermove', { clientX: xDe(1) });
  assert.doesNotMatch(g.aviso.textContent, /undefined/);
});

// ------------------------------------------------------------------- el día con el que nace la gráfica ---

test('si el día con el que nace no abre, el recuadro del detalle no se queda en «Cargando…»', async () => {
  for (const dia_inicial of ['2026-10-02', '2026-10-07', '2026-10-10', '']) {   // sin_dia, sin_copia, hoy y ninguno
    const g = await iniciar(undefined, { dia_inicial });
    assert.deepEqual(pedidas, [], dia_inicial);                // nada que pedir
    assert.equal(g.detalle.hidden, true, dia_inicial);         // y el «Cargando…» de la plantilla no se queda
    // Cuando la persona abre un día que sí abre, el recuadro vuelve y se llena.
    g.lienzo.disparar('click', { clientX: xDe(4) });
    await pasar();
    assert.equal(g.detalle.hidden, false, dia_inicial);
    assert.equal(g.detalle.html, '<p>detalle</p>', dia_inicial);
  }
});

test('si el día con el que nace abre, se pide y el recuadro se queda a la vista', async () => {
  pedidas = []; respuesta = resp(200, '<p>inicial</p>');
  const g = montar({ dia_inicial: '2026-10-09' });
  window.TwResultados.iniciar(g.raiz);
  await pasar();
  assert.deepEqual(pedidas, ['/x/dia?entrada=&fecha=2026-10-09']);
  assert.equal(g.detalle.hidden, false);
  assert.equal(g.detalle.html, '<p>inicial</p>');
});

// ---------------------------------------------------------------------------------- el error del detalle ---

test('un 400 con su motivo en palabras lo muestra la gráfica, como texto', async () => {
  const g = await iniciar(resp(400, 'Ese día no tiene datos completos.'));
  g.lienzo.disparar('click', { clientX: xDe(4) });
  await pasar();
  assert.equal(g.detalle.textContent, 'Ese día no tiene datos completos.');
  assert.equal(g.detalle.html, null);                              // jamás por innerHTML
});

test('un motivo con marcas no se inserta como HTML ni se muestra', async () => {
  const g = await iniciar(resp(400, '<img src=x onerror=alert(1)> Ese día no tiene datos'));
  g.lienzo.disparar('click', { clientX: xDe(4) });
  await pasar();
  assert.equal(g.detalle.textContent, TEXTOS.error_dia);
  assert.equal(g.detalle.html, null);
});

test('un 500, un 403 o la red caída siguen diciendo el aviso de siempre', async () => {
  for (const r of [resp(500, 'Error interno del servidor'), resp(403, 'Prohibido'), new Error('red caída')]) {
    const g = await iniciar(r);
    g.lienzo.disparar('click', { clientX: xDe(4) });
    await pasar();
    assert.equal(g.detalle.textContent, TEXTOS.error_dia);
  }
});

test('un 200 pone el fragmento del servidor', async () => {
  const g = await iniciar(resp(200, '<h4>Qué pasó</h4>'));
  g.lienzo.disparar('click', { clientX: xDe(4) });
  await pasar();
  assert.equal(g.detalle.html, '<h4>Qué pasó</h4>');
});
