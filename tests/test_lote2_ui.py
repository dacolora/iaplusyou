"""Regresiones de lote 2: JavaScript renderizado, sin navegador ni red."""
import json
import re
import subprocess

from tests.test_rutas_crear_director import app


def node(code):
    r = subprocess.run(['node', '-e', code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_pnd031_enlaces_cierran_antes_de_cambiar(app):
    from flask import render_template
    from types import SimpleNamespace
    with app['dashboard'].app.test_request_context():
        htmls = [render_template('_referente_recrear.html', cliente='acme', productos=[], r=SimpleNamespace(id=1)),
                 render_template('_referente_ficha.html', cliente='acme', r=SimpleNamespace(id=1), usos=2)]
    for html in htmls:
        handler = re.search(r'href="#(?:catalogo|creativeflowplus)" onclick="([^"]+)"', html).group(1)
        node("const assert=require('assert'); let orden=[]; const document={querySelector:()=>({click:()=>orden.push('tab')})}; const enlace={closest:()=>({close:()=>orden.push('close')})}; (function(){" + handler + "}).call(enlace); assert.deepStrictEqual(orden,['close','tab']);")


def test_pnd044_conserva_desmarcadas_y_cuenta_cero(app):
    html = app['c'].get('/cliente/acme').get_data(as_text=True)
    code = html.split('    var MESES =', 1)[1].split("    abrir.addEventListener", 1)[0]
    node(r"""
const assert=require('assert');
let checks=[], selected=[{value:'1',checked:true,dataset:{nombre:'a'}},{value:'2',checked:true,dataset:{nombre:'b'}}];
const marcadas=()=>selected, paises=[{value:'CO',checked:true}], nombre=null, cuenta={};
const moneda='COP', form={querySelector:()=>({value:'1'}),querySelectorAll:()=>[]};
const document={getElementById:()=>({}),createElement:()=>({innerHTML:'a'})};
const cuadricula={querySelectorAll:s=>s.includes(':checked')?checks.filter(c=>c.checked):checks,
set innerHTML(h){checks=[...h.matchAll(/name="combinaciones" value="([^"]+)"([^>]*)/g)].map(m=>({value:m[1],checked:m[2].includes('checked'),addEventListener:()=>{}}));}};
var MESES = """ + code + r"""
armarCuadricula(); checks.forEach(c=>c.checked=false); refrescarCuenta();
assert(cuenta.textContent.includes('0 anuncios'),cuenta.textContent);
armarCuadricula(); assert(checks.every(c=>!c.checked),'se marcaron otra vez');
selected.push({value:'3',checked:true,dataset:{nombre:'c'}}); armarCuadricula();
assert.deepStrictEqual(checks.map(c=>c.checked),[false,false,true]);
""")


def test_pnd030_hash_productos_abre_catalogo(app):
    html = app['c'].get('/cliente/acme').get_data(as_text=True)
    code = 'function enCatalogo() {' + html.split('function enCatalogo() {', 1)[1].split('    var arrancado', 1)[0]
    node("const assert=require('assert'); const location={hash:'#productos'}, localStorage={getItem:()=>null};" + code + "assert(enCatalogo()); location.hash='#referentes'; assert(!enCatalogo());")
