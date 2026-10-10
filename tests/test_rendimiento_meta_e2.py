"""Meta rendimiento E2 en la pestaña Rendimiento (integración con main, 2026-10-10, INT-1/INT-2).

Main construyó el «Diagnóstico», los «Segmentos» y la «Evaluación con IA» de Meta sobre la vieja pestaña «Meta» y salió
a producción; esa pestaña se había jubilado en la rama de Rendimiento. Estas pruebas vigilan que todo siga alcanzable en
Rendimiento con las reglas de plata intactas:

- el botón de la evaluación de Meta muestra el N y el precio que la ruta cobra (E2-R6), en «Todas», en una entrada y
  con cualquier periodo (0 = «Desde el inicio» evalúa los últimos 30 días y lo dice);
- la evaluación es de las cuentas de la entrada cuya fuente es Meta: una cuenta cuyos anuncios trae una tienda de
  Triple Whale (R5) la evalúa «Lo que hace ganar en tu cuenta», nunca las dos fuentes en un prompt;
- una entrada que ya no existe no se ensancha a «Todas» y no cobra nada;
- el Diagnóstico y los Segmentos son de toda la estructura de Meta del alcance (cubiertas incluidas).

Proyecto: una tienda de Triple Whale en Noruega (USD) que trae los anuncios de la cuenta de Noruega, y tres cuentas
de Meta en SEK: Noruega (cubierta), Suecia y Países Bajos (fuente Meta). Claude y Meta nunca se llaman."""
import re

import pytest

import db
import gastos
import proyectos
import triple_whale_tiendas
from meta_rendimiento import analisis
from meta_rendimiento import cuentas as mcuentas
from meta_rendimiento import datos as mdatos
from meta_rendimiento import panel as meta_panel
from pestana_rendimiento import panel as rend_panel
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_meta_rendimiento import _ad, _dia, _hace, _tasa
from tests.test_rutas_productos import _flashes
from triple_whale import datos as twdatos

TOKEN = "t-llave-de-prueba"   # llave-de-prueba
NO, SE, NL = "act_no", "act_se", "act_nl"
POST = {"Sec-Fetch-Site": "same-origin"}
PANEL = "/cliente/acme/rendimiento/panel"
EVALUAR = "/cliente/acme/meta-rendimiento/evaluar"


@pytest.fixture(autouse=True)
def _aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))


@pytest.fixture()
def mixto(app, monkeypatch):  # noqa: F811
    monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar", lambda c: {"token": TOKEN, "page_id": None})
    return app


def _sembrar(dias=40):
    """40 días: la tienda de Noruega (USD) con los anuncios de la cuenta de Noruega en su copia (R5: cubierta) y las
    tres cuentas de Meta con un ganador y perdedores cada una."""
    tid = triple_whale_tiendas.agregar("acme", "tw_llave_123", "acme-no.myshopify.com", "NO", moneda="USD")  # llave-de-prueba
    triple_whale_tiendas.actualizar_tienda("acme", tid, ultima_sincronizacion=db.ahora())
    mcuentas.elegir("acme", [{"id": NO, "name": "HappyFlops Norway", "currency": "SEK", "pais": "NO"},
                             {"id": SE, "name": "HappyFlops Sweden", "currency": "SEK", "pais": "SE"},
                             {"id": NL, "name": "HappyFlops Netherlands", "currency": "SEK", "pais": "NL"}])
    canal, pixel, tienda = [], [], []
    for n in range(dias):
        f = _hace(n)
        _tasa(f, 0.1, "SEK")
        # Noruega vende menos de lo que gasta: la regla `cuenta_roas_bajo` del Diagnóstico la marca «alta».
        mdatos.reemplazar_cuenta_dias("acme", NO, f, f, [_dia(f, 1000, 300, compras=1)])
        mdatos.reemplazar_cuenta_dias("acme", SE, f, f, [_dia(f, 300, 900, compras=4)])
        mdatos.reemplazar_cuenta_dias("acme", NL, f, f, [_dia(f, 250, 600, compras=3)])
        mdatos.reemplazar_anuncio_dias("acme", NO, f, f, [_ad(f, "o_gana", 100, 400, compras=2),
                                                          _ad(f, "o_p1", 900, 0)])
        mdatos.reemplazar_anuncio_dias("acme", SE, f, f, [_ad(f, "s_gana", 100, 900, compras=4),
                                                          _ad(f, "s_p1", 120, 0), _ad(f, "s_p2", 80, 0)])
        mdatos.reemplazar_anuncio_dias("acme", NL, f, f, [_ad(f, "n_gana", 100, 600, compras=3),
                                                          _ad(f, "n_p1", 150, 0)])
        for ad, gasto in (("o_gana", 10), ("o_p1", 90)):
            canal.append({"canal": "facebook-ads", "ad_id": ad, "fecha": f, "anuncio": ad, "gasto": gasto,
                          "impresiones": 3000, "cuenta_id": NO, "campana_id": "c1", "conjunto_id": "s1"})
            pixel.append({"canal": "facebook-ads", "ad_id": ad, "fecha": f, "pedidos": 1, "ingresos": gasto})
        tienda.append({"fecha": f, "gasto": 100, "ingresos": 80, "pedidos": 2})
    twdatos.reemplazar_anuncios_canal("acme", tid, _hace(dias - 1), _hace(0), canal)
    twdatos.reemplazar_anuncios_pixel("acme", tid, _hace(dias - 1), _hace(0), pixel)
    twdatos.reemplazar_tienda("acme", tid, _hace(dias - 1), _hace(0), tienda)
    return tid


def _panel(app, q=""):  # noqa: F811
    r = app["c"].get(PANEL + q)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _seccion(html, id_):
    i = html.index(f'id="{id_}"')
    return html[i:html.index("</section>", i)]


def _ocultos(html):
    """Los campos ocultos del formulario de la «Evaluación con IA» de Meta, como los mandaría el navegador."""
    seccion = _seccion(html, "meta-evaluacion")
    form = seccion[seccion.index("<form"):seccion.index("</form>")]
    return dict(re.findall(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"', form)), form


def _evaluaciones():
    return mdatos.evaluaciones("acme", limite=50)


def _tareas():
    import sqlalchemy as sa
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.tarea).where(db.tarea.c.tipo == "meta_rend_evaluar"))]


# ---------------------------------------------------------------------------------- lo que cobra ---

@pytest.mark.parametrize("entrada,dias", [("", 0), ("", 30), ("", 7), ("", 90), ("SE", 0), ("SE", 14)])
def test_el_boton_de_meta_cobra_lo_que_muestra(mixto, entrada, dias):
    """E2-R6 en Rendimiento: el N y el precio del botón son los que la ruta vuelve a calcular con `preparar` sobre las
    cuentas de la entrada cuya fuente es Meta, y lo que manda el botón crea la evaluación (una tarea, un intento) con
    esas cuentas. «Desde el inicio» (0) evalúa los últimos 30 días."""
    _sembrar()
    html = _panel(mixto, f"?entrada={entrada}&dias={dias}")
    campos, form = _ocultos(html)
    dias_eval = 30 if dias == 0 else dias
    ids = rend_panel.cuentas_evaluacion_meta("acme", entrada)
    assert set(ids) == ({SE, NL} if entrada == "" else {SE})             # nunca la cubierta (Noruega)
    n = len(analisis.preparar("acme", dias_eval, None, ids=ids)["muestra"])
    precio = gastos.estimar("evaluacion_meta", n=n)
    assert n >= 2 and campos == {"dias": str(dias_eval), "entrada": entrada, "n": str(n),
                                 "precio_visto": str(precio["usd_precio"])}
    assert f"Evaluar {n} anuncio(s) con IA · {precio['texto']}" in form
    if dias == 0:
        assert f"en los últimos {dias_eval} días." in form and "lo que ves arriba" not in form
    else:
        assert "Evalúa lo que ves arriba:" in form and f"últimos {dias_eval} días." in form
    r = mixto["c"].post(EVALUAR, data=campos, headers=POST)
    assert r.status_code == 302 and r.headers["Location"].endswith("#rendimiento")
    ev, = _evaluaciones()
    assert set(ev["cuentas"]) == set(ids) and len(ev["muestra"]) == n and ev["extra"]["dias"] == dias_eval
    assert ev["extra"]["parcial"] is (entrada == "")                      # «Todas» = 2 de las 3 cuentas
    tarea, = _tareas()
    assert tarea["max_intentos"] == 1 and tarea["job_id"] == "acme__meta_eval"


def test_con_otro_precio_o_otra_muestra_no_crea_ni_reserva_nada(mixto):
    """El mismo freno de la ruta de main (E2-R6) también con la entrada: un `n` que ya no es el de la muestra o un
    precio que cambió no crean ni reservan nada, y el aviso dice el precio de ahora."""
    import sqlalchemy as sa
    _sembrar()
    campos, _ = _ocultos(_panel(mixto))
    for cambio in ({"n": "99"}, {"precio_visto": "0.01"}, {"precio_visto": ""}):
        mixto["c"].post(EVALUAR, data=dict(campos, **cambio), headers=POST)
        assert _evaluaciones() == [] and _tareas() == []
    with db.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(db.reserva_saldo)).scalar() == 0
    assert any("Revisa el precio y vuelve a confirmar" in m for m in _flashes(mixto["c"]))


def test_la_lista_nombra_las_cuentas_de_una_evaluacion_parcial(mixto):
    """Desde «Todas» se evalúan 2 de las 3 cuentas: la evaluación no dice «Todas las cuentas» sino sus nombres."""
    _sembrar()
    campos, _ = _ocultos(_panel(mixto))
    mixto["c"].post(EVALUAR, data=campos, headers=POST)
    ev, = _evaluaciones()
    alcance = meta_panel.evaluacion_vista(ev)["alcance"]
    assert "HappyFlops Sweden" in alcance and "HappyFlops Netherlands" in alcance
    assert "Norway" not in alcance and "Todas las cuentas" not in alcance


def test_la_entrada_cubierta_por_la_tienda_no_ofrece_la_evaluacion_de_meta(mixto):
    """Noruega: su cuenta de Meta está dentro de la tienda (R5) y su fuente es Triple Whale: la sección lo dice y no
    ofrece botón; un envío armado no crea nada."""
    _sembrar()
    seccion = _seccion(_panel(mixto, "?entrada=NO"), "meta-evaluacion")
    assert "Las ventas de estas cuentas las cuenta Triple Whale" in seccion and "<form" not in seccion
    mixto["c"].post(EVALUAR, data={"entrada": "NO", "dias": "30", "n": "3", "precio_visto": "0.3"}, headers=POST)
    assert _evaluaciones() == [] and _tareas() == []
    assert any("Todavía no hay anuncios con datos suficientes" in m for m in _flashes(mixto["c"]))


def test_una_entrada_que_ya_no_existe_no_evalua_nada(mixto):
    """Una pestaña vieja (un país que se quitó) no se ensancha a «Todas»: nada se crea ni se cobra."""
    _sembrar()
    campos, _ = _ocultos(_panel(mixto))
    mixto["c"].post(EVALUAR, data=dict(campos, entrada="DK"), headers=POST)
    assert _evaluaciones() == [] and _tareas() == []
    assert any("Esa vista ya no existe" in m for m in _flashes(mixto["c"]))


# ------------------------------------------------------------------------------- lo que se ve ---

def test_las_secciones_de_meta_van_en_su_lugar(mixto):
    _sembrar()
    html = _panel(mixto)
    orden = ['id="meta-diagnostico"', "Tus anuncios</h3>", 'id="tw-ia"', 'id="meta-evaluacion"', "Campañas</h3>",
             'id="meta-segmentos"']
    posiciones = [html.index(marca) for marca in orden]
    assert posiciones == sorted(posiciones), list(zip(orden, posiciones))


def test_el_diagnostico_es_de_toda_la_estructura_de_meta(mixto):
    """El Diagnóstico habla de cómo está armada cada cuenta en Meta: también de la que cubre la tienda (Noruega vende
    menos de lo que gasta), en «Todas» y en su entrada; Suecia sola no la nombra."""
    _sembrar()
    todas = _seccion(_panel(mixto), "meta-diagnostico")
    assert "La cuenta vende menos de lo que gasta" in todas and "HappyFlops Norway" in todas
    noruega = _seccion(_panel(mixto, "?entrada=NO"), "meta-diagnostico")
    assert "La cuenta vende menos de lo que gasta" in noruega
    suecia = _seccion(_panel(mixto, "?entrada=SE"), "meta-diagnostico")
    assert "HappyFlops Norway" not in suecia


def test_sin_dias_copiados_de_meta_no_hay_secciones_de_meta(mixto):
    mcuentas.elegir("acme", [{"id": SE, "name": "HappyFlops Sweden", "currency": "SEK", "pais": "SE"}])
    html = _panel(mixto)
    for id_ in ("meta-diagnostico", "meta-evaluacion", "meta-segmentos"):
        assert f'id="{id_}"' not in html


def test_el_js_de_la_evaluacion_de_meta_vive_en_la_pestana():
    """Los <script> de un fragmento por fetch no corren: el de la vieja `_tab_meta.html` (anteriores por fetch y volver
    a pedir el panel cuando termina la barra) vive en `_tab_rendimiento.html`; el confirmar del precio es el mismo
    `form[data-confirmar]` de la galería."""
    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "templates", "_tab_rendimiento.html"), encoding="utf-8") as f:
        tab = f.read()
    assert "closest('[data-meta-ev]')" in tab and "T.errorEvaluacion" in tab
    terminado = tab[tab.index("cont.addEventListener('trabajo-terminado'"):]
    terminado = terminado[:terminado.index("});")]
    assert "closest('#meta-evaluacion')" in terminado and "cargar()" in terminado
    assert "form[data-confirmar]" in tab
