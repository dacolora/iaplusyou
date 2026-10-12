"""Comportamiento del código JS con DOM y fetch dobles, sin navegador ni red."""
import re
import pytest
import subprocess
from pathlib import Path

from tests.test_rutas_productos import app  # noqa: F401


@pytest.mark.parametrize("modo", ["panel", "foco"])
def test_pnd136_panel_fondo_enlace_blank_y_foco_tras_filtro(modo):
    programa = r'''
    const fs=require('fs'),assert=require('assert');const g=globalThis;g.window=g;
    const win={},doc={};g.addEventListener=(t,f)=>win[t]=f;g.innerWidth=1000;
    function nodo(a={}){return {attrs:a,firstChild:null,classList:{add(){},remove(){},toggle(){},contains(){return true}},
      getAttribute(n){return this.attrs[n]??null},setAttribute(n,v){this.attrs[n]=v},hasAttribute(n){return n in this.attrs},
      querySelector(){return null},querySelectorAll(){return []},addEventListener(t,f){this["on"+t]=f},appendChild(){},scrollIntoView(){},focus(){g.document.activeElement=this},isConnected:true};}
    const raiz=nodo({'data-url':'/resultados'}),panel=nodo(),cuerpo=nodo(),body=nodo();let cierres=0,focos=0;
    panel.open=false;panel.querySelector=()=>cuerpo;panel.close=()=>{cierres++;panel.open=false};panel.showModal=()=>panel.open=true;
    panel.contains=b=>!!b.enPanel;panel.getBoundingClientRect=()=>({left:100,right:500,top:100,bottom:500});
    raiz.contains=b=>!!(b&&b.enRaiz);raiz.querySelector=s=>s==='.cr-resultados-fragmento'?{}:null;
    const nuevo=nodo({'href':'#experimentos?dias=7'});nuevo.focus=()=>{focos++;g.document.activeElement=nuevo};
    raiz.querySelectorAll=s=>s==='[data-cr-filtro]'?[nuevo]:[];
    Object.defineProperty(raiz,'innerHTML',{set(v){if(raiz.contains(g.document.activeElement))g.document.activeElement=body}});
    g.document={readyState:'complete',activeElement:body,documentElement:{lang:'es'},addEventListener:(t,f)=>doc[t]=f,
      createElement:()=>nodo(),createElementNS:()=>nodo(),getElementById:id=>({'cr-resultados':raiz,'cr-panel':panel,'tab-experimentos':nodo(),'cr-textos':{textContent:'{}'}}[id]||null)};
    g.location={hash:'#experimentos',search:'',pathname:'/cliente/acme'};g.history={pushState:(s,t,u)=>g.location.hash=u,replaceState(){}};
    g.fetch=()=>Promise.resolve({ok:true,redirected:false,text:()=>Promise.resolve('<div class="cr-resultados-fragmento"></div>')});
    eval(fs.readFileSync('static/exp_resultados.js','utf8'));
    (async()=>{await new Promise(r=>setTimeout(r,0));
      if (MODO === 'panel') {
      panel.open=true;panel.onclick({target:panel,clientX:150,clientY:150});assert.equal(cierres,0,'clic vacío dentro cierra');
      panel.onclick({target:panel,clientX:50,clientY:150});assert.equal(cierres,1,'fondo externo no cierra');
      panel.open=true;
      const enlace={enPanel:true,target:'_blank',closest:s=>s==='a[href]'?enlace:null};
      doc.click({target:enlace});assert.equal(cierres,1,'enlace blank cierra');return; }
      panel.open=false;
      const b=nodo({'href':'#experimentos?dias=7','data-cr-filtro':''});b.enRaiz=true;b.tagName='A';b.closest=s=>s==='.cr-filtros'?{}:null;
      const target={closest:s=>s.includes('[data-cr-filtro]')?b:null};g.document.activeElement=b;
      doc.click({target,preventDefault(){},button:0});await new Promise(r=>setTimeout(r,0));
      assert.equal(focos,1,'foco perdido al reemplazar filtro');assert.equal(g.document.activeElement,nuevo);
    })().catch(e=>{console.error(e);process.exitCode=1});
    '''
    r = subprocess.run(["node", "-e", programa.replace('MODO', repr(modo))], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_pnd136_popstate_y_hash_de_misma_pestana_conservan_scroll(app):
    import json
    html = app["c"].get("/cliente/acme").data.decode()
    # El script de navegación de pestañas; se ejecutan sus funciones reales.
    script = next(s for s in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S) if "var STORAGE_KEY = 'tab-activa-" in s)
    funciones = '\n'.join(re.search(r"    function " + n + r"\([^\n]*\) \{.*?\n    \}", script, re.S).group() for n in ("activar", "desdeUbicacion"))
    programa = '''
    const vm=require('vm'),assert=require('assert');let saltos=0,activo='experimentos';
    const paneles={experimentos:{classList:{contains:()=>activo==='experimentos',toggle:(k,v)=>{if(v)activo='experimentos'}}},catalogo:{classList:{contains:()=>activo==='catalogo',toggle:(k,v)=>{if(v)activo='catalogo'}}}};
    const c={botones:[],paneles,STORAGE_KEY:'tab',localStorage:{setItem(){}},document:{getElementById:()=>null,querySelector:()=>null},window:{scrollTo:()=>saltos++},location:{hash:'#experimentos?dias=7'},resolver:v=>v};
    vm.createContext(c);vm.runInContext(CODIGO,c);
    c.desdeUbicacion({type:'popstate'});assert.equal(saltos,0,'popstate sube página');
    c.desdeUbicacion({type:'hashchange'});assert.equal(saltos,0,'filtro de misma pestaña sube página');
    c.location.hash='#catalogo';c.desdeUbicacion({type:'hashchange'});assert.equal(saltos,1);
    '''.replace('CODIGO',json.dumps(funciones))
    r = subprocess.run(["node", "-e", programa], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_pnd136_css_retirado_no_define_regla_nombre_code():
    codigo = Path("static/estilos/legado/02-barra-lateral-dentro-de-un-proyecto.css").read_text()
    selectores = [s.strip() for s in re.findall(r"([^{}]+)\{[^{}]*\}", re.sub(r"/\*.*?\*/", "", codigo, flags=re.S))]
    assert ".regla-nombre code" not in selectores
