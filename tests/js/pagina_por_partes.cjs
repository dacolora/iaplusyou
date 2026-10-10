// Ejecuta el JS renderizado de los shells; fetch y DOM locales, sin navegador.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const datos = JSON.parse(fs.readFileSync(0, 'utf8'));

class Nodo {
  constructor() { this.dataset = {}; this.eventos = {}; this.hijos = []; this.style = {}; this.isConnected = true; }
  addEventListener(tipo, fn) { (this.eventos[tipo] ||= []).push(fn); }
  dispatchEvent(ev) { (this.eventos[ev.type] || []).forEach(fn => fn(ev)); }
  appendChild(n) { this.hijos.push(n); }
  remove() { this.isConnected = false; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const evento = type => ({ type });

async function catalogo() {
  const detalle = new Nodo(), grilla = new Nodo(), precarga = new Nodo(), dialogo = new Nodo();
  const resumen = new Nodo(), buscador = new Nodo();
  resumen.textContent = 'Inicial'; buscador.value = '';
  detalle.tagName = datos.sel === 'plus' ? 'DIV' : 'DETAILS';
  detalle.dataset.modo = datos.sel === 'plus' ? 'checkbox' : 'radio';
  grilla.dataset.url = '/cliente/acme/catalogo/selector?sel=' + datos.sel;
  function opcion(v, checked) {
    const input = new Nodo(); input.value = v; input.checked = checked; input.dataset.nombre = 'Propio';
    const label = new Nodo(); label.dataset.nombre = 'propio'; label.querySelector = () => input;
    return label;
  }
  let opciones = [], previas = [opcion(datos.valor, true)];
  Object.defineProperty(precarga, 'innerHTML', {set: () => { previas = []; }});
  Object.defineProperty(grilla, 'innerHTML', {set: html => { opciones = html ? [opcion(datos.valor, true)] : []; grilla.hijos = []; }});
  grilla.querySelectorAll = sel => sel === 'input' ? opciones.map(l => l.querySelector()) : [];
  detalle.querySelector = () => precarga;
  detalle.querySelectorAll = sel => sel === 'input:checked'
    ? opciones.concat(previas).map(l => l.querySelector()).filter(i => i.checked) : opciones.concat(previas);
  detalle.closest = () => dialogo;
  const id = 'sel-' + datos.sel;
  const nodos = { [id]: detalle, [id + '-grilla']: grilla, [id + '-resumen']: resumen,
    [id + '-buscador']: buscador, [id + '-vacio']: new Nodo(), [id + '-add']: new Nodo(),
    [id + '-add-btn']: new Nodo(), [id + '-add-cancelar']: new Nodo() };
  const urls = [];
  let fallar = true;
  const contexto = {document: {getElementById: x => nodos[x], querySelectorAll: () => [], createElement: () => new Nodo()},
    location: {href: 'http://localhost/cliente/acme'}, URL, Event: class { constructor(type) { this.type = type; } },
    fetch: async url => { urls.push(url); return {ok: !fallar, redirected: false, text: async () => datos.html}; }};
  vm.runInNewContext(datos.script, contexto);
  assert.equal(urls.length, 0, 'el selector cerrado no pide el catálogo');
  const abrir = () => datos.sel === 'plus' ? dialogo.dispatchEvent(evento('catalogo-abrir'))
    : (detalle.open = true, detalle.dispatchEvent(evento('toggle')));
  abrir(); abrir();
  await tick();
  assert.equal(urls.length, 1, 'una sola petición mientras está cargando');
  assert.equal(grilla.hijos.length, 2, 'error en palabras y botón para reintentar');
  assert.equal(grilla.hijos[1].textContent, datos.reintentar);
  fallar = false;
  grilla.hijos[1].dispatchEvent(evento('click'));
  await tick();
  assert.equal(urls.length, 2);
  assert.equal(new URL(urls[1]).searchParams.get('marcado'), datos.valor);
  assert.equal(opciones[0].querySelector().checked, true, 'precarga conservada');
  assert.equal(previas.length, 0, 'no queda un input duplicado para el envío');
  abrir(); await tick();
  assert.equal(urls.length, 2, 'reabrir una grilla cargada no repite el fetch');
  opciones[0].querySelector().checked = false;
  detalle.dispatchEvent(evento('change'));
  assert.equal(resumen.textContent, 'Inicial', 'change delegado atiende los inputs insertados');
  buscador.value = 'no-coincide'; buscador.dispatchEvent(evento('input'));
  assert.equal(opciones[0].hidden, true, 'el filtro atiende las opciones remotas');
}

async function paginar() {
  const doc = new Nodo(), lista = new Nodo(); lista.tagName = datos.tipo === 'gasto' ? 'TBODY' : 'DIV';
  const acciones = new Nodo(); let mas = new Nodo();
  mas.dataset = {listaMas: datos.tipo === 'gasto' ? 'gasto-filas' : 'swaps-historial', url: '/pagina/24'};
  mas.parentElement = acciones;
  let llamadas = 0, fallar = true, sondeos = 0, envoltura = '';
  doc.getElementById = id => id === mas.dataset.listaMas ? lista : null;
  doc.createElement = tag => {
    const n = new Nodo();
    if (tag === 'template') {
      const siguiente = new Nodo(); siguiente.dataset = {...mas.dataset, url: '/pagina/48'};
      siguiente.parentElement = acciones;
      n.content = {querySelectorAll: () => Array.from({length: 24}, () => new Nodo()), querySelector: () => llamadas === 2 ? siguiente : null};
      Object.defineProperty(n, 'innerHTML', {set: html => { envoltura = html; }});
    }
    return n;
  };
  const instalar = () => { mas.replaceWith = siguiente => { mas = siguiente; instalar(); }; };
  instalar();
  vm.runInNewContext(datos.script, {document: doc, arrancarSondeos: () => sondeos++,
    fetch: async () => { llamadas++; return {ok: !fallar, redirected: false, text: async () => '<fragmento>'}; }});
  const click = () => doc.dispatchEvent({type: 'click', target: {closest: () => mas}});
  click(); click(); await tick();
  assert.equal(llamadas, 1);
  assert.equal(acciones.hijos.length, 1);
  assert.equal(mas.textContent, datos.reintentar);
  fallar = false; click(); await tick();
  assert.equal(lista.hijos.length, 24);
  assert.equal(sondeos, 1);
  if (datos.tipo === 'gasto') assert.equal(envoltura, '<table><tbody><fragmento></tbody></table>');
  assert.equal(mas.dataset.url, '/pagina/48');
  click(); await tick();
  assert.equal(lista.hijos.length, 48, 'delegación también en el botón que llegó por fetch');
  assert.equal(acciones.isConnected, false, 'fin de lista sin botón');
  doc.dispatchEvent({type: 'click', target: {closest: () => null}});
  assert.equal(llamadas, 3, 'los anuncios sueltos no disparan paginación');
}
(datos.tipo === 'catalogo' ? catalogo() : paginar()).catch(e => { console.error(e); process.exitCode = 1; });
