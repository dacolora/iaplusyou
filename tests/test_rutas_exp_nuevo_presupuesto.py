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
    assert "PLANTILLA_CONFIRMAR_LANZAR.replace('{resumen}', textoMaximo" in html
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
          addEventListener: (t, f) => { oyentes[t] = f; }, classList: {toggle() {}},
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
