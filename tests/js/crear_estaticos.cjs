// DOM derivado del HTML Flask. Ejecuta los módulos completos y los eventos reales.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const datos = JSON.parse(fs.readFileSync(0, 'utf8'));
class Nodo {
  constructor(tag='', attrs={}, textos=[], hijos=[]) {
    this.tagName = tag.toUpperCase(); this.attrs = {...attrs}; this.hijos = hijos;
    this._texto = textos.join(''); this.events = {}; this.style = {}; this.disabled = 'disabled' in attrs;
    this.hidden = 'hidden' in attrs; this.selected = 'selected' in attrs; this._checked = 'checked' in attrs;
    this._value = attrs.value || ''; this.dataset = {};
    for (const [k,v] of Object.entries(attrs)) if (k.startsWith('data-')) this.dataset[k.slice(5).replace(/-([a-z])/g, (_,c)=>c.toUpperCase())] = v;
    this.classList = {contains:c=>this.className.split(/\s+/).includes(c),
      add:c=>this.classList.toggle(c,true), remove:c=>this.classList.toggle(c,false),
      toggle:(c,on)=>{const set=new Set(this.className.split(/\s+/).filter(Boolean)); if(on===undefined)on=!set.has(c);on?set.add(c):set.delete(c);this.className=[...set].join(' ');}};
    hijos.forEach(h=>h.parentElement=this);
  }
  get id(){return this.attrs.id || '';}
  get name(){return this.attrs.name || '';}
  get type(){return this.attrs.type || '';}
  set type(v){this.attrs.type=v;}
  get className(){return this.attrs.class || '';}
  set className(v){this.attrs.class=v;}
  get checked(){return this._checked;}
  set checked(v){
    if(v && this.type==='radio') for(const n of raiz.todos()) if(n!==this && n.type==='radio' && n.name===this.name)n._checked=false;
    this._checked=v;
  }
  get value(){if(this.tagName==='SELECT')return this.selectedOptions[0]?.value || '';if(this.tagName==='TEXTAREA')return this._value || this._texto;return this._value;}
  set value(v){this._value=String(v);if(this.tagName==='SELECT')this.options.forEach(o=>o.selected=o.value===String(v));}
  get options(){return this.todos().filter(n=>n.tagName==='OPTION');}
  get selectedOptions(){const opts=this.options;return opts.filter(o=>o.selected).length?opts.filter(o=>o.selected):opts.slice(0,1);}
  get textContent(){return this._texto+this.hijos.map(n=>n.textContent).join('');}
  set textContent(v){this._texto=String(v);this.hijos=[];}
  get firstChild(){return this.hijos[0] || null;}
  get children(){return this.hijos;}
  get innerHTML(){return this._texto;}
  set innerHTML(v){this._texto=String(v);this.hijos=[];}
  get isConnected(){return true;}
  get form(){return this.closest('form');}
  get offsetParent(){return {};}
  get scrollHeight(){return 0;}
  get files(){return [];}
  todos(){return this.hijos.flatMap(h=>[h,...h.todos()]);}
  matches(selector){
    let s=selector;
    if(s.includes(':checked')){if(!this.checked)return false;s=s.replace(':checked','');}
    const atr=[...s.matchAll(/\[([\w-]+)(?:=["']?([^\]"']*)["']?)?\]/g)];
    for(const [,k,v] of atr)if(!(k in this.attrs) || (v!==undefined && this.attrs[k]!==v))return false;
    s=s.replace(/\[[^\]]*\]/g,'');
    const id=s.match(/#([\w-]+)/);if(id && this.id!==id[1])return false;
    for(const [,c] of s.matchAll(/\.([\w-]+)/g))if(!this.classList.contains(c))return false;
    const tag=s.match(/^[\w-]+/);return !tag || this.tagName===tag[0].toUpperCase();
  }
  querySelectorAll(s){return this.todos().filter(n=>s.split(',').some(part=>{
    const piezas=part.trim().split(/\s+(?=[^\]]*(?:\[|$))/);if(!n.matches(piezas.pop()))return false;
    let p=n.parentElement;for(const pieza of piezas.reverse()){while(p&&!p.matches(pieza))p=p.parentElement;if(!p)return false;p=p.parentElement;}return true;
  }));}
  querySelector(s){return this.querySelectorAll(s)[0] || null;}
  closest(s){for(let p=this;p;p=p.parentElement)if(p.matches(s))return p;return null;}
  setAttribute(k,v){this.attrs[k]=String(v);}
  getAttribute(k){return this.attrs[k];}
  removeAttribute(k){delete this.attrs[k];}
  hasAttribute(k){return k in this.attrs;}
  appendChild(n){n.parentElement=this;this.hijos.push(n);return n;}
  removeChild(n){this.hijos.splice(this.hijos.indexOf(n),1);}
  addEventListener(t,f){(this.events[t] ||= []).push(f);}
  dispatchEvent(e){if(!e.target)e.target=this;for(const f of this.events[e.type]||[])f(e);if(e.bubbles&&this.parentElement)this.parentElement.dispatchEvent(e);return true;}
  focus(){} scrollIntoView(){} pause(){} load(){}
}
function construir(n){return new Nodo(n.tag,n.attrs,n.textos,n.hijos.map(construir));}
const raiz=construir(datos.dom), peticiones=[], eventos=[];
const document={readyState:'loading',events:{},body:raiz.querySelector('body'),documentElement:raiz.querySelector('html'),
  getElementById:id=>raiz.todos().find(n=>n.id===id)||null,
  querySelector:s=>raiz.querySelector(s),querySelectorAll:s=>raiz.querySelectorAll(s),
  createElement:tag=>new Nodo(tag),createTextNode:t=>new Nodo('',{},[t]),
  addEventListener:Nodo.prototype.addEventListener,dispatchEvent:Nodo.prototype.dispatchEvent};
const almacenamiento={'crear-modo-acme':datos.guardado||null};
const context={document,console,URL,Event:class {constructor(type,o={}){this.type=type;Object.assign(this,o);}},
  CustomEvent:class {constructor(type,o={}){this.type=type;Object.assign(this,o);}},
  location:{hash:datos.hash},localStorage:{getItem:k=>almacenamiento[k]||null,setItem:(k,v)=>almacenamiento[k]=v,removeItem:k=>delete almacenamiento[k]},
  setTimeout:()=>1,clearTimeout(){},setInterval:()=>1,clearInterval(){},navigator:{},
  fetch:async url=>{peticiones.push(url);return {ok:true,status:200,json:async()=>({prompts:[],costo:''}),text:async()=>''};},
  confirm:()=>false,alert(){},FormData:class {},XMLHttpRequest:class {},isFinite,Date};
context.window=context;context.addEventListener=()=>{};context.scrollTo=()=>{};
vm.createContext(context);
document.addEventListener('crear:modo',e=>eventos.push(e.detail.modo));
// Los scripts sin defer corren al parsear su sección; los diferidos, antes de DOMContentLoaded.
for(const script of datos.scripts.filter(s=>!s.defer))vm.runInContext(script.codigo,context,{filename:script.archivo});
vm.runInContext(datos.modos,context,{filename:'modos-inline.js'});
assert.deepEqual(eventos,[], 'crear:modo se emitió antes de los módulos defer');
for(const script of datos.scripts.filter(s=>s.defer))vm.runInContext(script.codigo,context,{filename:script.archivo});
document.readyState='interactive';document.dispatchEvent({type:'DOMContentLoaded'});
const $=id=>document.getElementById(id);
assert.equal(eventos.length,1);
assert.equal(eventos[0],datos.modo);
if(datos.modo==='flowplus'){
  assert(peticiones.includes('/cliente/acme/guiones/panel'), 'Guiones perdió la apertura inicial');
  assert(peticiones.includes('/cliente/acme/guiones/prompts'), 'el chat perdió la apertura inicial');
}else assert.equal(peticiones.length,0,'se cargó un modo oculto');
const config=JSON.parse($('crear-compositor-datos').textContent), prefill=config.datos.prefill;
if(prefill?.texto)assert.equal($('fp-texto').value,prefill.texto);
if(prefill?.modelo)assert.equal($('fp-modelo').value,prefill.modelo);
if(prefill?.duracion)assert.equal($('fp-duracion').value,String(prefill.duracion));
for(const v of prefill?.productos_catalogo || [])assert($('form-flowplus').querySelector('input[name=productos_catalogo][value="'+v+'"]')?.checked);
assert($('fp-precio').textContent.includes('US$'), 'el botón perdió el precio');
// Cambiar modelo y tipo dispara los listeners extraídos y actualiza campo, pastilla y precio.
const modelo=$('form-flowplus').querySelector('input[name=modelo_video][value="kling_o3_pro"]');
assert(modelo, 'falta el modelo que ejercita el selector');
modelo.checked=true;modelo.dispatchEvent(new context.Event('change',{bubbles:true}));
assert.equal($('fp-modelo').value,'kling_o3_pro');assert($('fp-pill-modelo').textContent.includes(modelo.dataset.nombre));
const tipo=$('form-flowplus').querySelector('input[name=tipo][value="imagen"]');
tipo.checked=true;tipo.dispatchEvent(new context.Event('change',{bubbles:true}));
assert.equal($('fp-generar').textContent,config.textos.m02);assert($('fp-precio').textContent.includes('US$'));
// Audios cuenta texto y conserva el precio, aun estando oculto.
$('au-texto').value='abcd';$('au-texto').dispatchEvent(new context.Event('input'));
assert.equal(String($('au-contador').textContent),'4');assert.equal($('au-crear').disabled,false);
assert($('au-crear-precio').textContent.includes('US$'));
console.log('DOM, eventos, precarga y precios comprobados');
