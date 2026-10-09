"""NVP en la pestaña Triple Whale y en el Tablero (spec 2026-10-09-nvp-visitantes-nuevos §4.1 y §4.4): el KPI de la
tienda con su cambio en puntos, la columna de «Ver como tabla», el dato en cada tarjeta de análisis y las sumas de la
tienda que lee el Tablero. Siempre con el chip `cx.nvp` y las SUMAS del periodo; sin visitantes, «—» sin romper."""
from datetime import date

import pytest

import idiomas
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_experimentos import _resultados
from tests.test_rutas_triple_whale import _conectar, _hace, _sembrar, _tienda
from triple_whale import datos
from triple_whale import resultados as r

# Por día: (visitantes únicos, visitantes nuevos) de cada anuncio que el Pixel atribuye.
VISITAS_ANUNCIO = {"g1": (10, 8),        # 80 % → TOF
                   "g2": (3, 1),         # 30 visitantes en 10 días: pocos, sin etapa
                   "t1": (20, 4)}        # TikTok, 20 % → BOF


def _sembrar_con_visitas(dias=10, tienda=lambda dia: (100, 52)):
    """Los anuncios y la tienda de `_sembrar` (mismas cifras) más visitantes: por anuncio, VISITAS_ANUNCIO; la
    tienda, `tienda(dia)` = (únicos, nuevos) de hace `dia` días."""
    _sembrar(dias=dias)
    tid = _tienda()
    canal, pixel, filas_tienda = [], [], []
    for dia in range(dias):
        f = _hace(dia)
        for ad, gasto, imp, pedidos, ingresos, canal_ in (("g1", 20, 2000, 1, 120, "facebook-ads"),
                                                          ("g2", 15, 1500, 1, 90, "facebook-ads"),
                                                          ("p1", 40, 3000, 0, 0, "facebook-ads"),
                                                          ("p2", 30, 2500, 0, 0, "facebook-ads"),
                                                          ("n1", 1, 20, 0, 0, "facebook-ads"),
                                                          ("t1", 10, 1000, 0.5, 20, "tiktok-ads")):
            vis, nuevos = VISITAS_ANUNCIO.get(ad, (0, 0))
            canal.append({"canal": canal_, "ad_id": ad, "fecha": f, "anuncio": f"Anuncio {ad}", "campana": "Otoño",
                          "gasto": gasto, "impresiones": imp, "clics": imp // 50, "vistas_3s": imp // 3,
                          "thruplays": imp // 10, "utm_ok": ad != "p2"})
            pixel.append({"canal": canal_, "ad_id": ad, "fecha": f, "pedidos": pedidos, "ingresos": ingresos,
                          "visitantes": vis, "visitantes_nuevos": nuevos})
        unicos, nuevos_tienda = tienda(dia)
        filas_tienda.append({"fecha": f, "gasto": 120, "ingresos": 400, "pedidos": 5, "nc_pedidos": 2,
                             "visitantes": unicos, "visitantes_nuevos": nuevos_tienda})
    datos.reemplazar_anuncios_canal("acme", tid, _hace(dias - 1), _hace(0), canal)
    datos.reemplazar_anuncios_pixel("acme", tid, _hace(dias - 1), _hace(0), pixel)
    datos.reemplazar_tienda("acme", tid, _hace(dias - 1), _hace(0), filas_tienda)


def _panel(app, **query):  # noqa: F811
    resp = app["c"].get("/cliente/acme/triple-whale/panel", query_string=query)
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _kpi(html):
    ini = html.index("data-twr-nvp")
    return html[ini:html.index("</div>", ini)]


def _fila(html, nombre):
    tabla = html[html.index("tw-tabla tw-anuncios"):]
    ini = tabla.index(f"<strong>{nombre}</strong>")
    return tabla[ini:tabla.index("</tr>", ini)]


def _tarjeta(html, ad_id, canal="facebook-ads"):
    ini = html.index(f'id="tw-tarjeta-{canal}-{ad_id}"')
    return html[ini:html.index("</article>", ini)]


# ------------------------------------------------------------ cálculo ---

def _dias(n, vis, vnu, desde="2026-09-01"):
    serie = r.por_dia(desde, "2026-12-31", [])[:n]
    return [dict(d, ing=100.0, gas=50.0, ped=2.0, vis=float(vis), vnu=float(vnu)) for d in serie]


def test_tarjeta_nvp_suma_el_periodo_y_compara_en_puntos():
    with idiomas.en_idioma("es"):
        completos, previos = _dias(6, 100, 60), _dias(6, 100, 40)
        t = r.tarjeta_nvp("tienda", completos + _dias(1, 100, 100), completos, previos, True)
        assert (t["nuevos"], t["visitantes"]) == (460, 700)       # sumas, con hoy: 360 + 100 de 600 + 100
        assert t["variacion"] == pytest.approx(20.0) and t["variacion_texto"] == "20 pts"
        assert t["tono"] == "neutro"                               # una lectura: ninguna etapa es buena o mala
        assert r.tarjeta_nvp("tienda", completos, completos, _dias(6, 100, 55.5), True)["variacion_texto"] == "4,5 pts"
        assert r.tarjeta_nvp("tienda", completos, completos, _dias(6, 100, 59), True)["variacion_texto"] == "1 pt"


def test_tarjeta_nvp_no_compara_con_pocos_visitantes_ni_sin_comparacion():
    completos = _dias(6, 100, 60)
    assert r.tarjeta_nvp("tienda", completos, completos, _dias(6, 5, 1), True)["variacion"] is None   # 30 antes
    assert r.tarjeta_nvp("tienda", completos, completos, _dias(6, 100, 40), False)["variacion"] is None
    vacio = r.tarjeta_nvp("tienda", _dias(3, 0, 0), [], [], False)
    assert (vacio["nuevos"], vacio["visitantes"], vacio["variacion"]) == (0, 0, None)


def test_tarjeta_nvp_con_fuente_anuncios_usa_lo_que_atribuye_el_pixel():
    t = r.tarjeta_nvp("anuncios", _dias(6, 999, 999), _dias(6, 999, 999), _dias(6, 1, 1), True,
                      {"visitantes": 130, "visitantes_nuevos": 90})
    assert (t["nuevos"], t["visitantes"], t["variacion"]) == (90, 130, None)
    assert "Pixel" in t["ayuda"]


# --------------------------------------------------- pestaña Triple Whale ---

def test_kpi_de_la_tienda_tabla_y_tarjetas_pintan_el_nvp(app):  # noqa: F811
    _conectar()
    _sembrar_con_visitas()
    html = _panel(app)                                             # «Desde el inicio»: 1000 únicos, 520 nuevos
    kpi = _kpi(html)
    assert "Visitantes nuevos (NVP)" in kpi and 'class="chip-nvp chip-nvp-mof"' in kpi and "52&nbsp;%" in kpi
    assert "▲" not in kpi and "▼" not in kpi                       # desde el inicio no compara
    assert html.count('role="tab"') == 7                           # el NVP no es una pestaña de la gráfica
    # «Ver como tabla»: una columna NVP por anuncio.
    assert ">NVP</th>" in html
    assert 'chip-nvp chip-nvp-tof' in _fila(html, "Anuncio g1") and "80&nbsp;%" in _fila(html, "Anuncio g1")
    assert 'chip-nvp chip-nvp-pocos' in _fila(html, "Anuncio g2") and "33&nbsp;%" in _fila(html, "Anuncio g2")
    assert 'chip-nvp-vacio' in _fila(html, "Anuncio p1")
    assert 'chip-nvp chip-nvp-bof' in _fila(html, "Anuncio t1")
    # La tarjeta de análisis de cada anuncio.
    assert "Visitantes nuevos (NVP)" in _tarjeta(html, "g1") and "chip-nvp-tof" in _tarjeta(html, "g1")
    assert "chip-nvp-vacio" in _tarjeta(html, "p1")
    # La tarjeta que se repinta sola (ruta `tarjeta`) trae lo mismo.
    sola = app["c"].get("/cliente/acme/triple-whale/tarjeta/facebook-ads/g1").get_data(as_text=True)
    assert "chip-nvp-tof" in sola


def test_kpi_compara_el_nvp_con_el_periodo_anterior_en_puntos(app):  # noqa: F811
    _conectar()
    _sembrar_con_visitas(dias=20, tienda=lambda dia: (100, 60) if dia <= 6 else (100, 40))
    kpi = _kpi(_panel(app, dias=7))
    assert "60&nbsp;%" in kpi and "chip-nvp-mof" in kpi            # los 7 días con hoy
    assert "▲ 20 pts" in kpi                                       # 6 completos (60 %) contra los 6 anteriores (40 %)


def test_con_un_canal_el_kpi_es_lo_que_el_pixel_atribuye_a_sus_anuncios(app):  # noqa: F811
    _conectar()
    _sembrar_con_visitas()
    kpi = _kpi(_panel(app, canal="facebook-ads"))                  # g1 100/80 + g2 30/10 = 90 de 130
    assert "69&nbsp;%" in kpi and "chip-nvp-mof" in kpi and "Pixel" in kpi


def test_sin_visitantes_todo_dice_raya_sin_romper(app):  # noqa: F811
    _conectar()
    _sembrar()                                                     # la copia de antes de 0036: visitantes en 0
    html = _panel(app)
    assert "chip-nvp-vacio" in _kpi(html) and "Visitantes nuevos (NVP)" in _kpi(html)
    assert "chip-nvp-vacio" in _fila(html, "Anuncio g1") and "chip-nvp-vacio" in _tarjeta(html, "g1")
    assert "chip-nvp-tof" not in html and "chip-nvp-mof" not in html and "chip-nvp-bof" not in html
    assert "▲" not in _kpi(_panel(app, dias=7))


# ---------------------------------------------------------------- Tablero ---

def test_el_tablero_trae_las_sumas_de_visitantes_de_la_tienda(app):  # noqa: F811
    from triple_whale import panel
    _conectar()
    _sembrar_con_visitas()
    t = panel.resumen_total_tienda("acme", hoy=date.today())
    assert (t["visitantes"], t["visitantes_nuevos"]) == (1000, 520)
    html = _resultados(app["c"])
    assert "Tu tienda según Triple Whale" in html                    # el Tablero sigue pintando su bloque
    bloque = html[html.index("Tu tienda según Triple Whale"):]
    assert "chip-nvp-mof" in bloque and "52&nbsp;%" in bloque       # 520 de 1000: sumas, no promedios
