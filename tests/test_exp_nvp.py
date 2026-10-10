"""NVP en el centro de resultados de Experimentos (spec 2026-10-09-nvp-visitantes-nuevos §4.3; pedido del cliente de
HappyFlops, 2026-10-09): el % de visitantes nuevos de cada pieza (por el anuncio de Meta que creó Creatv), de cada
experimento y del filtro, con el chip `cx.nvp`. Solo se muestra; sin Triple Whale no se consulta ni se pinta."""
import re
from datetime import date, timedelta

import pytest

from tests.test_rutas_resultados import (AJAX, _experimento, _pieza_en,  # noqa: F401
                                         _proyectos_en_tmp, app)


def _tienda(cliente, dominio, pais="NO"):
    import triple_whale_tiendas
    triple_whale_tiendas.agregar(cliente, "llave-de-prueba", dominio, pais=pais)
    return [t["id"] for t in triple_whale_tiendas.tiendas(cliente) if t["dominio"] == dominio][0]


def _visitas(cliente, tienda_id, filas):
    """Filas del Pixel de Triple Whale: (ad_id, fecha, visitantes, nuevos[, canal])."""
    from triple_whale import datos
    registros = [dict(canal=(f[4] if len(f) > 4 else "facebook-ads"), ad_id=f[0], fecha=f[1], visitantes=f[2],
                      visitantes_nuevos=f[3]) for f in filas]
    fechas = sorted(r["fecha"] for r in registros)
    datos.reemplazar_anuncios_pixel(cliente, tienda_id, fechas[0], fechas[-1], registros)


def _hoy():
    import db
    return date.fromisoformat(db.ahora()[:10])


def _con_anuncio(base_temporal, eid, pais, n, ad_id):
    import experimentos as ex
    _pid, ep = _pieza_en(base_temporal, eid, pais=pais, n=n)
    ex.actualizar_pieza("acme", ep, meta_ad_id=ad_id, estado="activo")
    return ep


def _fila_de(html, ep):
    """La fila del ranking de esa pieza (de su <tr> a su </tr>)."""
    m = re.search(r'<tr class="cr-fila-[^"]*" data-cr-pieza="[^"]*/pieza/%d\?[^"]*">(.*?)</tr>' % ep, html, re.S)
    assert m, f"sin fila de la pieza {ep}"
    return m.group(1)


def _tarjeta_de(html, eid):
    m = re.search(r'<a data-cr-filtro href="#experimentos\?exp=%d"[^>]*cr-experimento[^>]*>(.*?)</a>' % eid, html, re.S)
    assert m, f"sin tarjeta del experimento {eid}"
    return m.group(1)


@pytest.fixture()
def con_tw(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    return _tienda("acme", "no.myshopify.com")


@pytest.fixture()
def sembrado(app, base_temporal, con_tw):
    """Dos piezas de un experimento (CO y MX) con visitas desiguales, para que la suma (65 %) no sea el promedio de
    porcentajes (50 %), más ruido que no debe contar: otro canal y otro proyecto con el mismo anuncio."""
    ayer = (_hoy() - timedelta(days=1)).isoformat()
    eid = _experimento("Prueba NVP", estado="corriendo", meta_campaign_id="cam_1")
    ep_a = _con_anuncio(base_temporal, eid, "CO", 1, "ad_a")
    ep_b = _con_anuncio(base_temporal, eid, "MX", 2, "ad_b")
    _visitas("acme", con_tw, [("ad_a", ayer, 300, 240), ("ad_b", ayer, 100, 20),
                              ("ad_a", ayer, 5000, 5000, "google-ads")])           # otro canal: no cuenta
    otra = _tienda("otro", "otro.myshopify.com")
    _visitas("otro", otra, [("ad_a", ayer, 9000, 9000)])                           # otro proyecto: no cuenta
    return {"eid": eid, "ep_a": ep_a, "ep_b": ep_b}


def test_cada_pieza_su_experimento_y_el_total_llevan_su_nvp(app, sembrado):
    html = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX).get_data(as_text=True)
    a, b = _fila_de(html, sembrado["ep_a"]), _fila_de(html, sembrado["ep_b"])
    assert "chip-nvp-tof" in a and "80&nbsp;%" in a and ">TOF<" in a and "240" in a and "300" in a
    assert "chip-nvp-bof" in b and "20&nbsp;%" in b and ">BOF<" in b
    # El experimento y el total: SUMA de visitantes (260 de 400 = 65 %), no el promedio de porcentajes (50 %).
    tarjeta = _tarjeta_de(html, sembrado["eid"])
    assert "chip-nvp-mof" in tarjeta and "65&nbsp;%" in tarjeta and ">MOF<" in tarjeta
    total = html[html.index("cr-nvp-total"):]
    total = total[:total.index("</p>")]
    assert "Visitantes nuevos (NVP)" in total and "65&nbsp;%" in total and "260" in total and "400" in total
    # Por país: cada uno lo suyo; y la columna NVP en las dos tablas.
    por_pais = html[html.index("Por país"):]
    por_pais = por_pais[:por_pais.index("</table>")]
    assert ">NVP<" in por_pais and "80&nbsp;%" in por_pais and "20&nbsp;%" in por_pais
    ranking = html[html.index('id="cr-ranking"'):]
    assert ">NVP<" in ranking[:ranking.index("</thead>")]


def test_el_panel_de_la_pieza_trae_su_nvp(app, sembrado):
    html = app["c"].get(f"/cliente/acme/experimentos/pieza/{sembrado['ep_b']}", headers=AJAX).get_data(as_text=True)
    linea = html[html.index("cr-pieza-nvp"):]
    linea = linea[:linea.index("</p>")]
    assert "chip-nvp-bof" in linea and "20&nbsp;%" in linea


def test_una_sola_consulta_de_visitantes_para_todas_las_piezas(app, base_temporal, sembrado, monkeypatch):
    from triple_whale import datos
    eid2 = _experimento("Otro", estado="corriendo", meta_campaign_id="cam_2")
    _con_anuncio(base_temporal, eid2, "CO", 3, "ad_c")
    _con_anuncio(base_temporal, eid2, "MX", 4, "ad_d")
    _pieza_en(base_temporal, eid2, pais="CO", n=5)                     # sin anuncio todavía: no se pregunta
    original, llamadas = datos.visitantes_por, []

    def contar(cliente, campo, ids, **kw):
        ids = list(ids)
        llamadas.append((cliente, campo, sorted(ids)))
        return original(cliente, campo, ids, **kw)
    monkeypatch.setattr(datos, "visitantes_por", contar)
    r = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX)
    assert r.status_code == 200 and "chip-nvp" in r.get_data(as_text=True)
    assert llamadas == [("acme", "ad_id", ["ad_a", "ad_b", "ad_c", "ad_d"])]
    llamadas.clear()
    app["c"].get(f"/cliente/acme/experimentos/pieza/{sembrado['ep_a']}", headers=AJAX)
    assert len(llamadas) == 1


def test_el_periodo_de_la_pantalla_manda_tambien_en_el_nvp(app, base_temporal, con_tw):
    hoy = _hoy()
    eid = _experimento("Periodo", estado="corriendo", meta_campaign_id="cam_1")
    ep = _con_anuncio(base_temporal, eid, "CO", 1, "ad_p")
    _visitas("acme", con_tw, [("ad_p", (hoy - timedelta(days=1)).isoformat(), 100, 80),
                              ("ad_p", (hoy - timedelta(days=60)).isoformat(), 100, 0)])
    todo = _fila_de(app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX).get_data(as_text=True), ep)
    assert "40&nbsp;%" in todo and ">MOF<" in todo                      # desde el inicio: 80 de 200
    semana = _fila_de(app["c"].get("/cliente/acme/experimentos/resultados?dias=7", headers=AJAX).get_data(as_text=True), ep)
    assert "80&nbsp;%" in semana and ">TOF<" in semana                  # 7 días: solo la visita de ayer


def test_con_triple_whale_y_sin_visitas_dice_raya(app, base_temporal, con_tw):
    eid = _experimento("Sin visitas", estado="corriendo", meta_campaign_id="cam_1")
    ep = _con_anuncio(base_temporal, eid, "CO", 1, "ad_nada")
    html = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX).get_data(as_text=True)
    assert "chip-nvp-vacio" in _fila_de(html, ep) and "chip-nvp-vacio" in _tarjeta_de(html, eid)


def test_sin_triple_whale_no_consulta_ni_pinta_el_nvp(app, base_temporal, monkeypatch):
    from triple_whale import datos

    def prohibida(*a, **kw):
        raise AssertionError("sin Triple Whale no se consultan visitantes")
    monkeypatch.setattr(datos, "visitantes_por", prohibida)
    eid = _experimento("Sin TW", estado="corriendo", meta_campaign_id="cam_1")
    ep = _con_anuncio(base_temporal, eid, "CO", 1, "ad_a")
    html = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX).get_data(as_text=True)
    assert "cr-resultados-fragmento" in html and _fila_de(html, ep)
    assert "chip-nvp" not in html and ">NVP<" not in html and "cr-nvp-total" not in html
    panel = app["c"].get(f"/cliente/acme/experimentos/pieza/{ep}", headers=AJAX).get_data(as_text=True)
    assert "cr-pieza-fragmento" in panel and "chip-nvp" not in panel and "cr-pieza-nvp" not in panel


def test_el_nvp_no_toca_el_decisor_ni_los_snapshots():
    """Solo se muestra: ni el decisor, ni el lanzador, ni los snapshots leen los visitantes de Triple Whale."""
    import pathlib
    raiz = pathlib.Path(__file__).resolve().parent.parent
    for archivo in ("decisor.py", "lanzador.py", "acciones.py", "modos.py"):
        texto = (raiz / archivo).read_text(encoding="utf-8")
        assert "visitantes_por" not in texto and "resultados.visitantes" not in texto, archivo
