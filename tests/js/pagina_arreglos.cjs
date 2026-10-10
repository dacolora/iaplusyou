// Árbol del HTML real: append/insert/replace mueven nodos y conservan su orden y dueño.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const datos = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const tick = () => new Promise(resolve => setImmediate(resolve));

class Elemento {
  constructor(tag, attrs = {}, texto = '') {
    this.tagName = tag.toUpperCase(); this.attrs = {...attrs}; this.children = []; this.parentElement = null;
    this.dataset = {}; Object.entries(attrs).filter(([k]) => k.startsWith('data-')).forEach(([k,v]) => {
      this.dataset[k.slice(5).replace(/-([a-z])/g, (_,c) => c.toUpperCase())] = v;
    });
    this.eventos = {}; this.style = {}; this._texto = texto; this.checked = 'checked' in attrs;
    this.hidden = 'hidden' in attrs; this.value = attrs.value || ''; this.open = 'open' in attrs;
  }
  get isConnected() { return this === doc || !!this.parentElement?.isConnected; }
  get textContent() { return this._texto + this.children.map(n => n.textContent).join(''); }
  set textContent(v) { this.children.slice().forEach(n => n.remove()); this._texto = v; }
  set innerHTML(html) {
    this.textContent = '';
    if (!html) return;
    const raiz = arbol(datos.fragmento);
    raiz.children.slice().forEach(n => this.appendChild(n));
  }
  set className(v) { this.attrs.class = v; }
  get href() { return this.attrs.href; }
  set href(v) { this.attrs.href = v; }
  addEventListener(tipo, fn) { (this.eventos[tipo] ||= []).push(fn); }
  dispatchEvent(ev) { ev.target ||= this; (this.eventos[ev.type] || []).forEach(fn => fn(ev)); return !ev.defaultPrevented; }
  appendChild(n) { n.remove(); n.parentElement = this; this.children.push(n); return n; }
  insertBefore(n, referencia) {
    if (referencia == null) return this.appendChild(n);
    assert.equal(referencia.parentElement, this);
    n.remove(); this.children.splice(this.children.indexOf(referencia), 0, n); n.parentElement = this; return n;
  }
  remove() {
    if (this.parentElement) this.parentElement.children.splice(this.parentElement.children.indexOf(this), 1);
    this.parentElement = null;
  }
  replaceWith(n) { const padre = this.parentElement; padre.insertBefore(n, this); this.remove(); }
  matches(s) {
    if (s.includes(':not([hidden])') && this.hidden) return false;
    s = s.replace(':not([hidden])', '');
    if (s.includes(':checked') && !this.checked) return false;
    s = s.replace(':checked', '');
    const tag = s.match(/^[\w-]+/); if (tag && tag[0].toUpperCase() !== this.tagName) return false;
    const id = s.match(/#([\w-]+)/); if (id && this.attrs.id !== id[1]) return false;
    if ([...s.matchAll(/\.([\w-]+)/g)].some(m => !(this.attrs.class || '').split(' ').includes(m[1]))) return false;
    return [...s.matchAll(/\[([\w-]+)(?:=["']?([^\]"']+)["']?)?\]/g)].every(m => {
      const v = m[1].startsWith('data-') ? this.dataset[m[1].slice(5).replace(/-([a-z])/g, (_,c) => c.toUpperCase())] : this.attrs[m[1]];
      return v !== undefined && (!m[2] || v === m[2]);
    });
  }
  closest(s) { for (let n = this; n; n = n.parentElement) if (n.matches(s)) return n; return null; }
  querySelectorAll(s) {
    const coincidir = n => s.split(',').some(parte => {
      const partes = parte.trim().split(/\s+/); if (!n.matches(partes.pop())) return false;
      let p = n.parentElement;
      while (partes.length) { const sel = partes.pop(); while (p && !p.matches(sel)) p = p.parentElement; if (!p) return false; p = p.parentElement; }
      return true;
    });
    return this.children.flatMap(n => [...(coincidir(n) ? [n] : []), ...n.querySelectorAll(s)]);
  }
  querySelector(s) { return this.querySelectorAll(s)[0] || null; }
}
function arbol(n) {
  const el = new Elemento(n.tag, n.attrs, n.texto);
  (n.hijos || []).forEach(h => el.appendChild(arbol(h))); return el;
}
const doc = arbol(datos.pagina);
doc.getElementById = id => doc.querySelector('#' + id);
let pedidos = 0;
doc.createElement = tag => {
  const el = new Elemento(tag);
  if (tag === 'template') Object.defineProperty(el, 'innerHTML', {set: () => { el.content = arbol(datos.fragmentos[pedidos - 1]); }});
  return el;
};
const contexto = {document: doc, URL, location: {href: 'http://localhost/cliente/acme'},
  Event: class { constructor(type) { this.type = type; } }, arrancarSondeos: () => {},
  fetch: async () => { pedidos++; return {ok: datos.tipo !== 'sesion', status: datos.respuesta === '403' ? 403 : 200,
    redirected: datos.respuesta === 'login', text: async () => '<fragmento>'}; }};
vm.runInNewContext(datos.script, contexto);
const click = boton => doc.dispatchEvent({type: 'click', target: boton});

async function ejecutar() {
  if (datos.tipo === 'envio') {
    const detalle = doc.getElementById('sel-clone'), form = detalle.closest('form');
    const archivo = form.querySelector('input[name="foto"]'); archivo.files = [{name: 'foto.jpg'}]; archivo.value = 'foto.jpg';
    assert.equal(detalle.open, false); assert.equal(pedidos, 0);
    const ev = {type: 'submit', preventDefault() { this.defaultPrevented = true; }};
    assert.equal(form.dispatchEvent(ev), false, 'sin producto no se envía el archivo');
    assert.equal(detalle.open, true, 'abre el selector para completar el producto');
    await tick();
    const radio = detalle.querySelector('input[name="producto_id"]'); assert.ok(radio);
    radio.checked = true; detalle.dispatchEvent({type: 'change'});
    assert.equal(form.dispatchEvent({type: 'submit', preventDefault() { this.defaultPrevented = true; }}), true);
    assert.equal(archivo.files[0].name, 'foto.jpg', 'la elección local del archivo se conserva');
  } else if (datos.tipo === 'orden') {
    const lista = doc.getElementById('swaps-historial');
    for (const cantidad of [48, 72, 74]) {
      click(doc.querySelector('[data-lista-mas="swaps-historial"]')); await tick();
      const tarjetas = lista.querySelectorAll('.swap-card'); assert.equal(tarjetas.length, cantidad);
      const mas = doc.querySelector('[data-lista-mas="swaps-historial"]');
      if (cantidad === 74) assert.equal(mas, null);
      else {
        const recorrido = doc.querySelectorAll('.swap-card, [data-lista-mas="swaps-historial"]');
        assert.ok(recorrido.indexOf(mas) > recorrido.indexOf(tarjetas.at(-1)), 'Ver más debe quedar debajo de la última tarjeta');
      }
    }
  } else {
    let contenedor;
    if (datos.sel === 'historial' || datos.sel === 'gasto') {
      const mas = doc.querySelector('[data-lista-mas="' + (datos.sel === 'gasto' ? 'gasto-filas' : 'swaps-historial') + '"]');
      contenedor = mas.parentElement; click(mas);
    } else {
      const detalle = doc.getElementById('sel-' + datos.sel); contenedor = doc.getElementById('sel-' + datos.sel + '-grilla');
      if (datos.sel === 'plus') detalle.closest('dialog').dispatchEvent({type: 'catalogo-abrir'});
      else { detalle.open = true; detalle.dispatchEvent({type: 'toggle'}); }
    }
    await tick();
    const enlace = contenedor.querySelector('a'); assert.ok(enlace, 'sesión vencida ofrece enlace para entrar');
    assert.equal(new URL(enlace.href, contexto.location.href).pathname, '/login');
    assert.ok(contenedor.querySelector('p').textContent.trim());
    assert.equal(contenedor.querySelector('button'), null, 'no queda un reintento perpetuo');
    assert.equal(pedidos, 1);
  }
}
ejecutar().catch(e => { console.error(e); process.exitCode = 1; });
