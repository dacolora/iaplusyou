"""«Nuevo experimento › Cuánto» (E2 R4, spec 2026-10-02 §5.1–§5.3): el servidor rechaza un reparto que supera el total
(aunque alguien arme el POST a mano), la pantalla pide UN total + días con el máximo a la vista y sin multiplicador,
y el enlace «← Volver a resultados» está siempre arriba. Plata: cada prueba falla si se rompe la regla que nombra."""
import json
import re

import pytest

from tests.test_experimentos_db import _pieza
from tests.test_rutas_bloque4 import _flashes
from tests.test_rutas_experimentos import FORM_PROBAR, app  # noqa: F401  (fixture `app`)


@pytest.fixture(autouse=True)
def _proyectos_en_tmp(monkeypatch, tmp_path):
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))


def _datos(base_temporal, **cambios):
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    return dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO", f"{clon}:MX"], **cambios), clon


# ---------- el servidor: suma(diario) × días ≤ total (+1 %) ----------

def test_exp_probar_rechaza_un_reparto_que_supera_el_total_y_no_deja_nada(app, base_temporal):
    import experimentos as ex
    # 2 países × 20.000 al día × 7 días = 280.000, pero el total dice 200.000
    datos, clon = _datos(base_temporal, tope_total="200000")
    r = app["c"].post("/cliente/acme/experimentos/probar", data=datos)
    assert r.status_code == 302 and r.headers["Location"] == "/cliente/acme/experimentos/nuevo?piezas=%d" % clon
    assert ex.cargar("acme") == [] and app["encolados"] == []
    mensaje = " ".join(_flashes(app["c"]))
    assert "El reparto supera el total" in mensaje
    # dice de dónde salió la cuenta: el diario, los días, el máximo y el total que se puso
    assert "40.000" in mensaje and "7 días" in mensaje and "280.000" in mensaje and "200.000" in mensaje


def test_exp_probar_rechaza_pasarse_de_a_poco_y_acepta_el_margen_de_redondeo(app, base_temporal):
    import experimentos as ex
    # 280.000 de máximo: 270.000 × 1,01 = 272.700 no alcanza → rechaza
    datos, _ = _datos(base_temporal, tope_total="270000")
    app["c"].post("/cliente/acme/experimentos/probar", data=datos)
    assert ex.cargar("acme") == [] and app["encolados"] == []
    # 277.500 × 1,01 = 280.275 ≥ 280.000 → entra (solo el 1 % que el spec deja por redondeo)
    datos, _ = _datos(base_temporal, tope_total="277500")
    app["c"].post("/cliente/acme/experimentos/probar", data=datos)
    (e,) = ex.cargar("acme")
    assert e["tope_total"] == 277500.0 and [p["presupuesto_dia"] for p in e["paises"]] == [20000.0, 20000.0]
    assert [t["tipo"] for t in app["encolados"]] == ["exp_lanzar"] and app["encolados"][0]["max_intentos"] == 1


def test_exp_probar_acepta_exactamente_el_total_que_la_pantalla_propone(app, base_temporal):
    import experimentos as ex
    # lo que la pantalla manda para 300.000 COP en 7 días con 1 pieza en CO y MX: floor(300000/2/7) = 21428 por país
    datos, _ = _datos(base_temporal, tope_total="300000", presupuesto_CO="21428", presupuesto_MX="21428")
    app["c"].post("/cliente/acme/experimentos/probar", data=datos)
    (e,) = ex.cargar("acme")
    assert e["tope_total"] == 300000.0 and e["dias"] == 7
    assert 21428 * 2 * 7 <= 300000


def test_exp_probar_sigue_pidiendo_el_minimo_de_meta_y_cifras_enteras_en_cop(app, base_temporal):
    import experimentos as ex
    datos, _ = _datos(base_temporal, tope_total="500000", presupuesto_CO="3999")          # < 4.000 COP
    app["c"].post("/cliente/acme/experimentos/probar", data=datos)
    assert any("no alcanza el mínimo de Meta" in m for m in _flashes(app["c"]))
    datos, _ = _datos(base_temporal, tope_total="500000", presupuesto_CO="20000.5")       # centavos de peso: no
    app["c"].post("/cliente/acme/experimentos/probar", data=datos)
    assert any("cifras enteras" in m for m in _flashes(app["c"]))
    datos, _ = _datos(base_temporal, tope_total="inf")
    app["c"].post("/cliente/acme/experimentos/probar", data=datos)
    assert ex.cargar("acme") == [] and app["encolados"] == []


def test_exp_probar_en_dolares_lleva_centavos_pero_no_mas_de_dos_decimales(app, base_temporal, monkeypatch):
    import experimentos as ex
    monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar", lambda c: {"moneda": "USD"})
    datos, _ = _datos(base_temporal, tope_total="100", presupuesto_CO="7.14", presupuesto_MX="7.14")   # 14,28 × 7 = 99,96
    app["c"].post("/cliente/acme/experimentos/probar", data=datos)
    (e,) = ex.cargar("acme")
    assert [p["presupuesto_dia"] for p in e["paises"]] == [7.14, 7.14]
    datos, _ = _datos(base_temporal, tope_total="100", presupuesto_CO="7.145", presupuesto_MX="7.14")
    app["c"].post("/cliente/acme/experimentos/probar", data=datos)
    assert len(ex.cargar("acme")) == 1 and any("dos decimales" in m for m in _flashes(app["c"]))


def test_exp_crear_tampoco_acepta_un_reparto_que_supera_el_total(app):
    import experimentos as ex
    from tests.test_rutas_experimentos import FORM
    app["c"].post("/cliente/acme/experimentos/nuevo", data=dict(FORM, tope_total="100000"))   # 280.000 > 100.000
    assert ex.cargar("acme") == []
    assert any("El reparto supera el total" in m for m in _flashes(app["c"]))
    app["c"].post("/cliente/acme/experimentos/nuevo", data=FORM)                                # 280.000 ≤ 500.000
    assert len(ex.cargar("acme")) == 1


def test_el_tope_de_la_campana_que_dice_la_pantalla_es_el_que_lanzador_aplica():
    import lanzador
    assert lanzador.minimo_tope_campana("COP") == 400000.0 and lanzador.minimo_tope_campana("USD") == 100.0
    assert lanzador.minimo_tope_campana("GBP") == lanzador.SPEND_CAP_MINIMO_USD       # moneda sin lista: el mínimo en dólares


# ---------- la pantalla ----------

def _pagina(app, base_temporal, pieza=True, extra=""):
    if pieza:
        _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    r = app["c"].get("/cliente/acme/experimentos/nuevo" + extra)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _paso(html, n):
    """El HTML de un paso de `exp_probar` (<section data-paso="n">…</section>)."""
    ini = html.index(f'<section data-paso="{n}"')
    return html[ini:html.index("</section>", ini)]


def test_el_paso_cuanto_pide_un_total_y_dias_con_tres_atajos_rotulados_sugerencia(app, base_temporal):
    paso = _paso(_pagina(app, base_temporal), 2)
    assert 'name="tope_total"' in paso and 'name="dias"' in paso
    for atajo in ("Prueba rápida", "Estándar", "Fuerte"):
        assert atajo in paso
    assert paso.count("data-atajo=") == 3 and paso.count(">Sugerencia<") == 3
    # un forma de ajustar (barra y cifra), el total mínimo que arregla un país bajo el mínimo y el reparto a mano
    assert 'type="range"' in paso and 'id="exp-total-barra"' in paso
    assert "Usar ese total" in paso and 'id="exp-usar-minimo"' in paso
    assert "Ajustar reparto" in paso and 'name="presupuesto_CO"' in paso and "Volver al reparto automático" in paso


def test_lo_grande_es_el_maximo_que_puede_gastar_y_el_reparto_sin_multiplicador(app, base_temporal):
    html = _pagina(app, base_temporal)
    for paso in (2, 3):
        p = _paso(html, paso)
        assert 'class="exp-maximo"' in p and 'class="exp-dia"' in p and 'class="exp-anuncios"' in p
        assert "Nada gasta hasta que pulses Activar" in p
    # las frases que arma el JS: el máximo, el diario por país y «N anuncios (X piezas en Y países)»
    for frase in ("Máximo que puede gastar: {total} en {n} días", "Máximo que puede gastar: {total} en {n} día",
                  "≈ {dia} al día", "{anuncios} ({piezas} en {paises})"):
        assert json.dumps(frase) in html, frase           # el JS las recibe como cadenas JSON
    # la confirmación de «Lanzar» repite el máximo
    assert "PLANTILLA_CONFIRMAR_LANZAR.replace('{resumen}', textoConfirmar" in html
    # ninguna línea con multiplicador («3 piezas × 2 países = …») ni conectores sueltos para armarla
    assert "CONECTOR_X" not in html and "CONECTOR_IGUAL" not in html and "CONECTOR_HASTA" not in html and "CONECTOR_TOPE" not in html
    assert not re.search(r"\d+\s*(piezas?|anuncios?|países|país)\s*[×x]\s*\d+", html)
    assert "tope total" not in html.lower() and "Presupuesto planificado" not in html


def test_la_cuenta_se_lee_de_un_solo_archivo_y_no_se_repite_en_la_pagina(app, base_temporal):
    html = _pagina(app, base_temporal)
    assert "presupuesto_exp.js" in html and "window.PresupuestoExp" in html
    # la plantilla ya no trae su propia copia de la fórmula (la de presupuesto_exp.js es la que prueba la paridad)
    assert "total * pesos" not in html and "anuncios * dias" not in html and "P.repartir(" in html and "P.atajos(" in html
    assert 'data-minimo="4000"' in html and 'data-moneda="COP"' in html


def test_la_pantalla_dice_que_los_dias_cuentan_desde_la_primera_activacion_y_hasta_donde_llega_el_tope(app, base_temporal):
    html = _pagina(app, base_temporal)
    for paso in (2, 3):
        p = _paso(html, paso)
        assert "empiezan a contar cuando actives el experimento por primera vez" in p
        assert "la fecha de cierre no se mueve" in p
        assert "tope de la campaña desde 400.000 COP" in p       # lanzador.minimo_tope_campana('COP')
    assert "no desde la activación" not in html and "desde el lanzamiento, no" not in html


def test_nuevo_experimento_tiene_su_enlace_para_volver_a_resultados_siempre_arriba(app, base_temporal):
    html = _pagina(app, base_temporal)
    enlace = '<a class="exp-volver" href="/cliente/acme#experimentos">← Volver a resultados</a>'
    assert enlace in html
    # va antes que el título y que cualquier paso: es la salida de una pantalla sin menú lateral
    assert html.index(enlace) < html.index("<h2>Nuevo experimento</h2>") < html.index('id="exp-galeria"')
    assert html.count("Volver a resultados") == 1


def test_el_nombre_de_cada_pais_y_su_bandera_viajan_a_la_pantalla_para_decir_cual_queda_bajo_el_minimo(app, base_temporal):
    html = _pagina(app, base_temporal)
    assert re.search(r'class="exp-pais-check" data-bandera="[^"]+" data-nombre="[^"]+"', html)


# ---------- la lógica de la página (el trozo inline que cuenta el presupuesto), con un DOM de mentira ----------

import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ARNES_PAGINA = r"""
const assert = require('assert');
var window = {}; window.PresupuestoExp = require(%(cuenta)s);
const nodo = () => { const hijos = {}, oyentes = {};
  return {value: '', hidden: false, textContent: '', dataset: {}, oyentes, checked: false, readOnly: false,
          addEventListener: (t, f) => { oyentes[t] = f; }, classList: {toggle() {}}, setAttribute() {},
          querySelector: (s) => hijos[s] || (hijos[s] = nodo()), querySelectorAll: () => []}; };
const campos = {}, ids = {};
const campo = (s, v) => campos[s] || (campos[s] = Object.assign(nodo(), {value: v === undefined ? '4000' : v}));
const form = {querySelector: (s) => campo(s), querySelectorAll: () => [], dataset: {minimo: '4000', moneda: 'COP'}};
const document = {getElementById: (i) => ids[i] || (ids[i] = nodo()), createElement: () => ({innerHTML: 'a'}), documentElement: {lang: 'es'}};
const pais = (value) => Object.assign(nodo(), {value, checked: true, dataset: {bandera: value, nombre: value === 'CO' ? 'Colombia' : 'México'}});
const paises = [pais('CO'), pais('MX')];
const selected = [1, 2, 3].map((n) => Object.assign(nodo(), {value: String(n), checked: true, dataset: {nombre: 'p' + n}}));
const marcadas = () => selected, nombre = null, moneda = 'COP', minimo = 4000;
const pasoVisible = () => 2;
let checks = [];
const cuadricula = {querySelectorAll: (s) => s.includes(':checked') ? checks.filter((c) => c.checked) : checks, set innerHTML(h) {}};
campo('[name=tope_total]', '1400000'); campo('[name=dias]', '7');
var MESES = %(codigo)s
const texto = (id, clase) => ids[id].querySelector(clase).textContent;
%(guion)s
"""


def _en_la_pagina(app, base_temporal, guion):
    _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    html = app["c"].get("/cliente/acme/experimentos/nuevo").get_data(as_text=True)
    codigo = html.split("    var MESES =", 1)[1].split("    abrir.addEventListener", 1)[0]
    import json
    programa = _ARNES_PAGINA % {"cuenta": json.dumps(os.path.join(RAIZ, "static", "presupuesto_exp.js")), "codigo": codigo, "guion": guion}
    r = subprocess.run([shutil.which("node"), "-e", programa], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[-1500:]


@pytest.mark.skipif(not shutil.which("node"), reason="sin Node no se corre el JS (el VPS no lo tiene)")
def test_la_pagina_pinta_el_maximo_el_reparto_por_pais_y_los_anuncios_sin_multiplicador(app, base_temporal):
    _en_la_pagina(app, base_temporal, r"""
refrescarCuenta();
assert.strictEqual(texto('exp-resumen', '.exp-maximo'), 'Máximo que puede gastar: 1.400.000 COP en 7 días');
assert.strictEqual(texto('exp-resumen', '.exp-dia'), '≈ 200.000 COP al día · CO 100.000 · MX 100.000');
assert.strictEqual(texto('exp-resumen', '.exp-anuncios'), '6 anuncios (3 piezas en 2 países)');
assert.strictEqual(texto('exp-resumen-final', '.exp-maximo'), texto('exp-resumen', '.exp-maximo'));    // Revisar repite lo mismo
for (const id of ['exp-resumen', 'exp-resumen-final']) for (const c of ['.exp-maximo', '.exp-dia', '.exp-anuncios']) assert(!/[×=]/.test(texto(id, c)), texto(id, c));
// lo que se manda: el diario de cada país × los días nunca pasa del total
assert.strictEqual(Number(campo('[name=presupuesto_CO]').value) * 2 * 7 <= 1400000, true);
// atajos: 4× / 8× / 15× el mínimo por anuncio en 4 / 7 / 10 días, a dos cifras
const atajos = window.PresupuestoExp.atajos({CO: 3, MX: 3}, 4000);
assert.deepStrictEqual(atajos, [{total: 390000, dias: 4}, {total: 1400000, dias: 7}, {total: 3600000, dias: 10}]);
""")


@pytest.mark.skipif(not shutil.which("node"), reason="sin Node no se corre el JS (el VPS no lo tiene)")
def test_la_pagina_avisa_el_pais_bajo_el_minimo_con_el_total_que_lo_arregla_y_no_deja_seguir(app, base_temporal):
    _en_la_pagina(app, base_temporal, r"""
campo('[name=tope_total]').value = '100000'; campo('[name=dias]').value = '30';      // 1.666 al día por país: bajo los 4.000 de Meta
assert.notStrictEqual(problema(), '');
assert.strictEqual(ids['exp-minimo'].hidden, false);
assert(ids['exp-minimo'].textContent.includes('4.000 COP al día') && ids['exp-minimo'].textContent.includes('240.000 COP'), ids['exp-minimo'].textContent);
assert(ids['exp-minimo'].textContent.includes('Colombia') && ids['exp-minimo'].textContent.includes('México'));
assert.strictEqual(ids['exp-usar-minimo'].hidden, false);
// «Usar ese total» pone justo el total mínimo, vuelve al reparto automático y ya se puede seguir
ids['exp-usar-minimo'].oyentes.click();
assert.strictEqual(campo('[name=tope_total]').value, 240000);
assert.strictEqual(campo('[name=presupuesto_CO]').value, 4000);
assert.strictEqual(ids['exp-minimo'].hidden, true);
assert.strictEqual(problema(), '');
// un peso menos y vuelve a faltar
campo('[name=tope_total]').value = '239999'; refrescarCuenta();
assert.notStrictEqual(problema(), '');
""")


@pytest.mark.skipif(not shutil.which("node"), reason="sin Node no se corre el JS (el VPS no lo tiene)")
def test_la_pagina_recalcula_el_total_al_ajustar_el_reparto_a_mano_y_pide_cifras_enteras_en_cop(app, base_temporal):
    _en_la_pagina(app, base_temporal, r"""
refrescarCuenta();
manual = true;                                                                       // la persona editó el diario de un país
campo('[name=presupuesto_CO]').value = '30000'; campo('[name=presupuesto_MX]').value = '48750'; campo('[name=dias]').value = '4';
refrescarCuenta();
assert.strictEqual(campo('[name=tope_total]').value, (30000 + 48750) * 4);          // el total es suma × días
assert.strictEqual(texto('exp-resumen', '.exp-maximo'), 'Máximo que puede gastar: 315.000 COP en 4 días');
assert.strictEqual(problema(), '');
// en COP no hay centavos: 30000.5 se avisa con palabras en vez de dejar que el servidor lo rechace
campo('[name=presupuesto_CO]').value = '30000.5';
assert(problema().includes('cifras enteras'), problema());
// volver al reparto automático devuelve el reparto parejo del mismo total
campo('[name=presupuesto_CO]').value = '30000';
ids['exp-reparto-auto'].oyentes.click();
assert.strictEqual(campo('[name=presupuesto_CO]').value, 39375); assert.strictEqual(campo('[name=presupuesto_MX]').value, 39375);
""")


# ---------- el script REAL de la página completo, con un DOM mínimo (ronda de arreglo 1 de R4) ----------
# La prueba de arriba evalúa solo el trozo del presupuesto; esta corre TODO el <script> de la plantilla, como el navegador:
# así se ve lo que pasa entre la galería, la barra «Probar en Meta» y los pasos (p. ej. dos `var` con el mismo nombre).

_DOM = r"""
const assert = require('assert');
const registro = [];
function Nodo(id) { this.id = id; this.hidden = false; this.textContent = ''; this.value = ''; this.checked = false; this.disabled = false;
  this.dataset = {}; this.oyentes = {}; this.atributos = {}; this.hijos = {}; this.listas = {}; this.classList = {toggle() {}, add() {}, remove() {}}; }
Nodo.prototype.addEventListener = function (t, f) { (this.oyentes[t] = this.oyentes[t] || []).push(f); };
Nodo.prototype.disparar = function (t, ev) { const e = ev || {preventDefault() { this.prevenido = true; }, prevenido: false}; (this.oyentes[t] || []).forEach((f) => f(e)); return e; };
Nodo.prototype.querySelector = function (s) { return this.hijos[s] || (this.hijos[s] = new Nodo(s)); };
Nodo.prototype.querySelectorAll = function (s) { return this.listas[s] || []; };
Nodo.prototype.setAttribute = function (n, v) { this.atributos[n] = v; };
Nodo.prototype.scrollIntoView = function () {};
const ids = {};
const nodo = (id) => ids[id] || (ids[id] = new Nodo(id));
const con = (n, props) => Object.assign(n, props || {});

const piezas = [1, 2, 3].map((n) => con(new Nodo('pieza' + n), {value: String(n), dataset: {pais: '', imagen: '0', nombre: 'p' + n, final: '0', doctrinaN: '0'}}));
const co = con(new Nodo('CO'), {value: 'CO', dataset: {bandera: 'CO', nombre: 'Colombia'}});
const mx = con(new Nodo('MX'), {value: 'MX', dataset: {bandera: 'MX', nombre: 'México'}});
const paisesNodos = [co, mx];
const galeria = nodo('exp-galeria');
galeria.listas['input[name=piezas]'] = piezas; galeria.listas['.exp-tarjeta'] = []; galeria.listas['[data-filtro]'] = [];
const form = nodo('exp-probar');
form.hidden = true; form.dataset = {minimo: '4000', moneda: 'COP', topeCampana: '400000'};
const total = con(new Nodo('tope_total'), {value: ''}), dias = con(new Nodo('dias'), {value: '7'});
const campoCO = con(new Nodo('presupuesto_CO'), {value: '4000'}), campoMX = con(new Nodo('presupuesto_MX'), {value: '4000'});
form.hijos['[name=tope_total]'] = total; form.hijos['[name=dias]'] = dias;
form.hijos['[name=presupuesto_CO]'] = campoCO; form.hijos['[name=presupuesto_MX]'] = campoMX;
form.listas['[name^=presupuesto_]'] = [campoCO, campoMX]; form.listas['.exp-pais-check'] = paisesNodos;
const pasos = [1, 2, 3].map((n) => con(new Nodo('paso' + n), {dataset: {paso: String(n)}, hidden: n !== 1}));
form.listas['[data-paso]'] = pasos;
form.querySelector = function (s) { return s === '[data-paso]:not([hidden])' ? (pasos.filter((p) => !p.hidden)[0] || null) : Nodo.prototype.querySelector.call(this, s); };
const botones = [];
const ir = (n) => { const b = con(new Nodo('ir' + n), {dataset: {ir: String(n)}}); botones.push(b); return b; };
const [ir2, ir3, ir3b] = [ir(2), ir(3), ir(3)];
form.listas['[data-ir]'] = botones;
const atajos = [0, 1, 2].map((i) => con(new Nodo('atajo' + i), {dataset: {atajo: String(i)}}));
form.listas['[data-atajo]'] = atajos;
const cuadricula = nodo('exp-cuadricula');
let celdas = [];
Object.defineProperty(cuadricula, 'innerHTML', {set(h) { celdas = [...h.matchAll(/name="combinaciones" value="([^"]+)"([^>]*)/g)].map((m) => con(new Nodo('c' + m[1]), {value: m[1], checked: m[2].includes('checked')})); }});
cuadricula.querySelectorAll = (s) => s.includes(':checked') ? celdas.filter((c) => c.checked) : celdas;
const alertas = [], confirmaciones = [];
globalThis.alert = (m) => alertas.push(m);
globalThis.confirm = (m) => { confirmaciones.push(m); return false; };
globalThis.location = {hash: '', search: %(busqueda)s};
globalThis.document = {getElementById: nodo, createElement: () => ({set textContent(v) { this.innerHTML = v; }}), documentElement: {lang: 'es'}};
globalThis.window = {PresupuestoExp: require(%(cuenta)s)};
// ---- el script de la página, tal cual
(0, eval)(%(script)s);
// ---- ayudas del escenario
const marcar = (n, v) => { n.checked = v === undefined ? true : v; n.disparar('change'); };
const escribir = (n, v) => { n.value = String(v); n.disparar('input'); };
const clic = (n) => n.disparar('click');
const texto = (id, clase) => nodo(id).querySelector(clase).textContent;
const abrirPasos = () => { clic(nodo('exp-abrir-pasos')); marcar(co); marcar(mx); };
%(guion)s
"""


def _script_de_la_pagina(app, base_temporal, guion, busqueda="''"):
    """Renderiza «Nuevo experimento» y corre su <script> (el del formulario, con `exp-abrir-pasos`) sobre un DOM mínimo."""
    import json
    for n in range(3):
        _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado=f"cf_{n}")
    html = app["c"].get("/cliente/acme/experimentos/nuevo").get_data(as_text=True)
    scripts = [m for m in re.findall(r"<script>(.*?)</script>", html, re.S) if "exp-abrir-pasos" in m]
    assert len(scripts) == 1
    programa = _DOM % {"cuenta": json.dumps(os.path.join(RAIZ, "static", "presupuesto_exp.js")), "script": json.dumps(scripts[0]),
                       "guion": guion, "busqueda": busqueda}
    r = subprocess.run([shutil.which("node"), "-e", programa], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, (r.stderr or r.stdout)[-2500:]


_NODE = pytest.mark.skipif(not shutil.which("node"), reason="sin Node no se corre el JS (el VPS no lo tiene)")


@_NODE
def test_sin_piezas_en_la_direccion_marcar_una_muestra_la_barra_probar_en_meta(app, base_temporal):
    """C1: `var barra` estaba declarada dos veces (la barra «Probar en Meta» y el deslizador del total): la segunda pisaba a
    la primera y, entrando por «+ Nuevo experimento» (sin ?piezas=), «Probar en Meta →» no aparecía nunca."""
    _script_de_la_pagina(app, base_temporal, r"""
const barra = nodo('exp-barra'), deslizador = nodo('exp-total-barra');
assert.strictEqual(barra.hidden, true, 'sin piezas marcadas la barra está oculta');
marcar(piezas[0]);
assert.strictEqual(barra.hidden, false, 'marcar una pieza debe mostrar la barra «Probar en Meta»');
assert.strictEqual(nodo('exp-barra-texto').textContent, '1 pieza marcada');
assert.strictEqual(deslizador.hidden, false, 'el deslizador del total no es la barra: no se toca desde la galería');
marcar(piezas[1]); assert.strictEqual(nodo('exp-barra-texto').textContent, '2 piezas marcadas');
marcar(piezas[0], false); marcar(piezas[1], false);
assert.strictEqual(barra.hidden, true, 'sin piezas la barra vuelve a ocultarse');
assert.strictEqual(nodo('exp-barra-texto').textContent, '0 piezas marcadas');
// y el camino completo: marcar → «Probar en Meta» → países → «Cuánto» → «Revisar»
marcar(piezas[0]); marcar(piezas[2]);
abrirPasos(); assert.strictEqual(form.hidden, false);
clic(ir2); assert.strictEqual(pasos[1].hidden, false);
assert(Number(total.value) > 0, 'al entrar a «Cuánto» ya hay una sugerencia');
clic(ir3); assert.strictEqual(pasos[2].hidden, false, alertas.join('|'));
""")


@_NODE
def test_con_piezas_en_la_direccion_desmarcarlas_todas_oculta_la_barra_y_el_formulario(app, base_temporal):
    _script_de_la_pagina(app, base_temporal, r"""
assert.strictEqual(nodo('exp-barra').hidden, false);
assert.strictEqual(nodo('exp-barra-texto').textContent, '2 piezas marcadas');
abrirPasos(); assert.strictEqual(form.hidden, false);
marcar(piezas[0], false); marcar(piezas[1], false);
assert.strictEqual(nodo('exp-barra').hidden, true); assert.strictEqual(form.hidden, true);
assert.strictEqual(nodo('exp-barra-texto').textContent, '0 piezas marcadas');
""", busqueda="'?piezas=1,2'")


@_NODE
def test_por_debajo_del_minimo_de_tope_de_campana_dice_planeado_y_no_maximo_y_el_confirm_lo_repite(app, base_temporal):
    """G1: sin tope duro en Meta (total < lanzador.minimo_tope_campana) no se puede decir «Máximo que puede gastar»."""
    _script_de_la_pagina(app, base_temporal, r"""
marcar(piezas[0]); abrirPasos(); clic(ir2);
// total bajo: 100.000 COP < 400.000 (lo que Meta acepta como tope de campaña en COP)
escribir(total, 100000);
const bajo = texto('exp-resumen', '.exp-maximo');
assert.strictEqual(bajo, 'Presupuesto planeado: 100.000 COP en 7 días');
assert(!bajo.includes('Máximo'), bajo);
const linea = texto('exp-resumen', '.exp-aviso-tope');
assert(linea.includes('Meta no pone un tope duro') && linea.includes('400.000 COP') && linea.includes('100.000 COP') && linea.includes('al día'), linea);
// el mismo texto en Revisar y en el confirm de «Lanzar»
clic(ir3); assert.strictEqual(pasos[2].hidden, false, alertas.join('|'));
assert.strictEqual(texto('exp-resumen-final', '.exp-maximo'), bajo);
assert.strictEqual(texto('exp-resumen-final', '.exp-aviso-tope'), linea);
form.disparar('submit');
assert.strictEqual(confirmaciones.length, 1);
assert(confirmaciones[0].includes(bajo) && confirmaciones[0].includes(linea) && !confirmaciones[0].includes('Máximo'), confirmaciones[0]);
""")


@_NODE
def test_desde_el_minimo_de_tope_de_campana_sigue_diciendo_maximo_que_puede_gastar_y_el_confirm_tambien(app, base_temporal):
    _script_de_la_pagina(app, base_temporal, r"""
marcar(piezas[0]); abrirPasos(); clic(ir2);
escribir(total, 400000);                                      // justo el mínimo: lanzador manda spend_cap con >=
assert.strictEqual(texto('exp-resumen', '.exp-maximo'), 'Máximo que puede gastar: 400.000 COP en 7 días');
assert.strictEqual(texto('exp-resumen', '.exp-aviso-tope'), '');
escribir(total, 399999);
assert(texto('exp-resumen', '.exp-maximo').startsWith('Presupuesto planeado'), texto('exp-resumen', '.exp-maximo'));
escribir(total, 1400000);
clic(ir3); form.disparar('submit');
assert(confirmaciones[0].includes('Máximo que puede gastar: 1.400.000 COP en 7 días') && !confirmaciones[0].includes('planeado'), confirmaciones[0]);
""")


@_NODE
def test_un_total_borrado_a_mano_no_se_rellena_solo_y_no_deja_seguir(app, base_temporal):
    """M5: la sugerencia «Estándar» se pone al ENTRAR al paso; vaciar el campo lo deja vacío, avisa y no deja pasar."""
    _script_de_la_pagina(app, base_temporal, r"""
marcar(piezas[0]); abrirPasos();
assert.strictEqual(total.value, '', 'antes de entrar a «Cuánto» no hay cifra');
clic(ir2);
assert(Number(total.value) > 0, 'al entrar se sugiere el Estándar');
const sugerido = total.value;
escribir(total, '');                                          // la persona borra el campo
assert.strictEqual(total.value, '', 'no se vuelve a llenar en cada tecla');
assert.strictEqual(nodo('exp-total-aviso').hidden, false);
assert.strictEqual(texto('exp-resumen', '.exp-maximo'), '');
clic(ir3);
assert.strictEqual(pasos[2].hidden, true, 'sin total no se pasa a Revisar'); assert.strictEqual(alertas[alertas.length - 1], 'Escribe el total.');
assert.strictEqual(total.value, '');
escribir(total, 250000); assert.strictEqual(nodo('exp-total-aviso').hidden, true);
// volver a entrar con el campo vacío vuelve a sugerir (es «entrar al paso»)
escribir(total, ''); clic(ir3); clic(ir2); assert.strictEqual(total.value, sugerido);
""")


@_NODE
def test_el_deslizador_alinea_su_minimo_al_paso_y_no_mueve_su_tope_al_escribir_un_total_grande(app, base_temporal):
    """M2/M3/M4: min alineado al paso (390.000 cae en una marca), max estable aunque el total escrito lo pase, y la
    moneda en el texto que lee el lector de pantalla."""
    _script_de_la_pagina(app, base_temporal, r"""
marcar(piezas[0]); marcar(piezas[1]); marcar(piezas[2]); abrirPasos(); clic(ir2);
const d = nodo('exp-total-barra');
const paso = Number(d.step), max0 = Number(d.max), min0 = Number(d.min);
assert(paso >= 1 && max0 > 0 && min0 > 0);
assert.strictEqual(min0 %% paso, 0, 'el mínimo cae en una marca del paso'); assert.strictEqual(max0 %% paso, 0);
assert(min0 >= window.PresupuestoExp.repartir(1, 7, {CO: 3, MX: 3}, 'COP', 4000).total_minimo, 'nunca ofrece un total bajo el mínimo de Meta');
escribir(total, 390000);
assert.strictEqual(Number(d.value), 390000); assert.strictEqual(390000 %% paso, 0, 'una cifra redonda cae justo en una marca');
assert(d.atributos['aria-valuetext'].includes('390.000') && d.atributos['aria-valuetext'].includes('COP'), d.atributos['aria-valuetext']);
escribir(total, 99999999);                                    // más del doble de «Fuerte»: el tope NO se corre
assert.strictEqual(Number(d.max), max0); assert.strictEqual(Number(d.step), paso);
escribir(total, 400000); assert.strictEqual(Number(d.max), max0);
// al cambiar el número de anuncios sí se fija otro rango
marcar(piezas[2], false); marcar(piezas[1], false); assert.notStrictEqual(Number(d.max), max0);
""".replace("%%", "%"))


def test_solo_un_resumen_anuncia_sus_cambios_al_lector_de_pantalla(app, base_temporal):
    """M4: `aria-live` en el resumen del paso «Cuánto» (donde se edita) y en ningún otro: dos regiones vivas repetían todo."""
    html = _pagina(app, base_temporal)
    assert html.count('aria-live="polite"') == 1
    assert '<div class="exp-resumen" id="exp-resumen" aria-live="polite">' in html
    assert '<div class="exp-resumen" id="exp-resumen-final">' in html


def test_la_pantalla_manda_a_la_pagina_desde_que_total_hay_tope_de_campana(app, base_temporal):
    """G1: la página decide «máximo» o «planeado» con el mismo umbral que usa lanzar (lanzador.minimo_tope_campana)."""
    html = _pagina(app, base_temporal)
    assert 'data-tope-campana="400000.0"' in html
    assert "Presupuesto planeado: {total} en {n} días" not in html     # va como JSON (con \u00e9…): se mira por su forma
    for frase in ("Presupuesto planeado: {total} en {n} días", "Presupuesto planeado: {total} en {n} día",
                  "Meta no pone un tope duro a la campaña por debajo de {tope}: Creatv reparte {total} en presupuestos diarios por país (≈ {dia} al día)."):
        assert json.dumps(frase) in html, frase
    assert "(suma × días)" not in html and "suma × días" not in html
