"""PND-317 (decisión 2026-10-13: «arreglarlo una vez para las tres barras»): las barras de pastillas `cat-tabs` que
cambian de panel (Sprints · Nicho, Catálogo, Configuración y su «Conectar tienda») son pestañas de verdad para un
lector de pantalla (tablist, tab con `aria-controls`, tabpanel con `aria-labelledby`) y se manejan con las flechas.
Las marcas van en las plantillas; el comportamiento, una sola vez en `static/pestanas.js`."""
import json
import os
import shutil
import subprocess

import pytest

from tests.html_lote7 import HTML
from tests.js_de_pagina import con_script_estatico
from tests.test_rutas_nicho import app  # noqa: F401  (fixture)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BARRAS = {"sprints-subs": 2, "cat-tabs": None, "config-apartados": None, "tienda-tipos": 4}


def _pagina(cliente):
    r = cliente.get("/cliente/acme")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _como(app, usuario, rol, cliente):  # noqa: F811
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"], s["rol"], s["cliente"] = usuario, rol, cliente
    return c


def _barras(html):
    raiz = HTML(html).raiz
    por_id = {}

    def recorrer(n):
        if n.attrs.get("id"):
            por_id.setdefault(n.attrs["id"], []).append(n)
        for h in n.hijos:
            recorrer(h)
    recorrer(raiz)
    barras = {}

    def buscar(n):
        clases = (n.attrs.get("class") or "").split()
        if "cat-tabs" in clases and n.attrs.get("role") == "tablist":
            clave = next((c for c in clases if c != "cat-tabs"), n.attrs.get("id"))
            barras[clave] = n
        for h in n.hijos:
            buscar(h)
    buscar(raiz)
    return barras, por_id


def _pestanas(barra):
    out = []

    def recorrer(n):
        if n.attrs.get("role") == "tab":
            out.append(n)
        for h in n.hijos:
            recorrer(h)
    recorrer(barra)
    return out


@pytest.mark.parametrize("quien", ["admin", "cliente"])
def test_cada_barra_es_un_tablist_con_sus_tabs_y_sus_paneles(app, quien):  # noqa: F811
    c = app["c"] if quien == "admin" else _como(app, "user_acme", "cliente", "acme")
    barras, por_id = _barras(_pagina(c))
    assert set(BARRAS) <= set(barras), sorted(barras)
    for clave, cuantas in BARRAS.items():
        barra = barras[clave]
        assert "data-pestanas" in barra.attrs, clave
        assert barra.attrs.get("aria-label"), clave            # el lector de pantalla dice qué barra es
        tabs = _pestanas(barra)
        assert tabs and (cuantas is None or len(tabs) == cuantas), (clave, len(tabs))
        for t in tabs:
            assert t.tag == "button" and t.attrs.get("aria-selected") in ("true", "false"), (clave, t.attrs)
            tid, panel_id = t.attrs.get("id"), t.attrs.get("aria-controls")
            assert tid and len(por_id[tid]) == 1, (clave, tid)   # ids únicos en la página
            paneles = por_id.get(panel_id) or []
            assert len(paneles) == 1, (clave, panel_id)
            panel = paneles[0]
            assert panel.attrs.get("role") == "tabpanel" and panel.attrs.get("aria-labelledby") == tid, (clave, panel.attrs)


def test_configuracion_de_un_cliente_no_apunta_a_apartados_que_no_ve(app):  # noqa: F811
    """«Puesta a punto» es solo del admin: sin su pestaña tampoco hay panel huérfano, y al revés."""
    barras, por_id = _barras(_pagina(_como(app, "user_acme", "cliente", "acme")))
    ids = [t.attrs["aria-controls"] for t in _pestanas(barras["config-apartados"])]
    assert "config-ap-puesta" not in ids and "config-ap-puesta" not in por_id
    paneles = [i for i, nodos in por_id.items() if nodos[0].attrs.get("role") == "tabpanel" and i.startswith("config-ap-")]
    assert sorted(paneles) == sorted(ids)


def test_la_pagina_carga_el_script_comun_de_pestanas(app):  # noqa: F811
    html = _pagina(app["c"])
    con_script_estatico(html, "pestanas.js")      # falla si no está enlazado exactamente una vez


_NODE = pytest.mark.skipif(not shutil.which("node"), reason="sin Node no se corre el JS")

_DOM = r"""
const assert = require('assert');
function clases(lista) { const s = new Set(lista); return {
  contains: (c) => s.has(c), add: (c) => { s.add(c); cambio(); }, remove: (c) => { s.delete(c); cambio(); },
  toggle: (c, on) => { if (on === undefined ? !s.has(c) : on) s.add(c); else s.delete(c); cambio(); } }; }
let observadores = [];
function cambio() { observadores.forEach((f) => f()); }
global.MutationObserver = function (f) { this.observe = () => observadores.push(f); };
let enfocada = null;
function pestana(nombre, activa, extra) {
  const t = Object.assign({nombre, attrs: {role: 'tab'}, hidden: false, disabled: false, clics: 0,
    setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
    focus() { enfocada = this; }, closest() { return this; },
    click() { this.clics++; tabs.forEach((o) => o.classList.toggle('activo', o === this)); }}, extra || {});
  t.classList = clases(activa ? ['activo'] : []);
  return t;
}
const tabs = [pestana('a', false), pestana('b', true), pestana('oculta', false, {hidden: true}), pestana('c', false)];
let oyente = null;
const lista = {attrs: {}, getAttribute(k) { return this.attrs[k]; }, setAttribute(k, v) { this.attrs[k] = v; },
  querySelectorAll: () => tabs, addEventListener: (t, f) => { if (t === 'keydown') oyente = f; }};
global.window = {};
global.document = {readyState: 'complete', querySelectorAll: () => [lista], addEventListener() {}};
SCRIPT
function tecla(desde, key, mods) {
  const ev = Object.assign({key, target: desde, prevenida: false, preventDefault() { this.prevenida = true; }}, mods || {});
  oyente(ev); return ev;
}
const estado = () => tabs.map((t) => [t.nombre, t.attrs['aria-selected'], t.attrs.tabindex].join(':')).join(' ');
const salida = {};
salida.inicio = estado();
// La clase la cambia el script de la pantalla (hash, lo guardado): aria-selected y tabindex la siguen solos.
tabs[0].classList.toggle('activo', true); tabs[1].classList.toggle('activo', false);
salida.por_clase = estado();
let ev = tecla(tabs[0], 'ArrowRight');
salida.derecha = [enfocada.nombre, estado(), ev.prevenida, tabs[1].clics];
ev = tecla(tabs[1], 'ArrowRight');                       // salta la oculta
salida.salta_oculta = [enfocada.nombre, estado()];
ev = tecla(tabs[3], 'ArrowRight');                       // de la última vuelve a la primera
salida.vuelta = [enfocada.nombre, estado()];
ev = tecla(tabs[0], 'ArrowLeft');
salida.izquierda = [enfocada.nombre];
ev = tecla(tabs[3], 'Home'); salida.inicio_tecla = enfocada.nombre;
ev = tecla(tabs[0], 'End'); salida.fin_tecla = enfocada.nombre;
const clicsAntes = tabs.map((t) => t.clics).join(',');
ev = tecla(tabs[3], 'ArrowRight', {ctrlKey: true}); salida.con_ctrl = [ev.prevenida, tabs.map((t) => t.clics).join(',') === clicsAntes];
ev = tecla(tabs[3], 'Enter'); salida.otra_tecla = ev.prevenida;
console.log(JSON.stringify(salida));
"""


@_NODE
def test_el_script_sigue_la_clase_activo_y_mueve_con_las_flechas():
    js = open(os.path.join(RAIZ, "static", "pestanas.js"), encoding="utf-8").read()
    r = subprocess.run([shutil.which("node"), "-e", _DOM.replace("SCRIPT", js)], capture_output=True, text=True,
                       timeout=30)
    assert r.returncode == 0, r.stderr[-2000:]
    s = json.loads(r.stdout)
    # Una sola pestaña seleccionada y en el orden de Tab; las demás fuera (tabindex itinerante).
    assert s["inicio"] == "a:false:-1 b:true:0 oculta:: c:false:-1"
    assert s["por_clase"] == "a:true:0 b:false:-1 oculta:: c:false:-1"
    assert s["derecha"] == ["b", "a:false:-1 b:true:0 oculta:: c:false:-1", True, 1]
    assert s["salta_oculta"] == ["c", "a:false:-1 b:false:-1 oculta:: c:true:0"]
    assert s["vuelta"][0] == "a" and s["izquierda"] == ["c"]
    assert s["inicio_tecla"] == "a" and s["fin_tecla"] == "c"
    assert s["con_ctrl"] == [False, True] and s["otra_tecla"] is False
