"""Revisión final de E1 de la pestaña Rendimiento (2026-10-10, revisor): las cifras que ve el cliente.

- R1 (enmienda A7): con SOLO tiendas de Triple Whale en «Todas», «Por país» arranca donde arrancan los Resultados de
  Triple Whale (cada tienda desde su primer día) y no hay «Desde el …» común; el inicio común de R7 es solo para mezclas.
- R2 (R6 en «Por país»): la cifra principal va en la moneda común de todas las filas (USD si no la hay); una fila sin
  USD dice «USD no disponible» y aparece el aviso de la página.
- R3: pruebas que matan las mutaciones que sobrevivieron (22–28).
- R4: el panel hace el mismo número de consultas con 12 y con 24 anuncios por fuente.
- R5: una sola barra para las copias en curso del alcance.
- R6: «Lo que necesita tu atención» junta las dos fuentes sin quitar textos repetidos, con lo «alta» primero.
- R7: el filtro «Canal» solo ofrece canales con gasto en el periodo.
- R8: el estado vacío sin cuentas y la ayuda del retorno de la mezcla.
"""
import re
from datetime import date, timedelta

import pytest

import db
import idiomas
import triple_whale_tiendas
from meta_rendimiento import cuentas as mcuentas
from meta_rendimiento import datos as mdatos
from pestana_rendimiento import panel
from tests.test_rendimiento_resumen import _llave_de_cifrado, _sembrar  # noqa: F401  (fixture autouse: cifra la llave)
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_meta_rendimiento import _ad, _dia, _tasa
from tests.test_rutas_rendimiento import meta_on  # noqa: F401  (fixture)
from triple_whale import datos as twdatos

HOY = date.today()


def _hace(n):
    return (HOY - timedelta(days=n)).isoformat()


@pytest.fixture()
def meta_conectado(monkeypatch):
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "cargar", lambda c: {"token": "t-llave-de-prueba", "page_id": None})  # llave-de-prueba


@pytest.fixture()
def sin_meta(monkeypatch):
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "cargar", lambda c: {})


def _ctx(**k):
    with idiomas.en_idioma("es"):
        return panel.contexto("acme", hoy=HOY, **k)


def _panel(app, q=""):  # noqa: F811
    return app["c"].get("/cliente/acme/rendimiento/panel" + q).data.decode()


def _tienda_con_dias(dominio, pais, dias, moneda="USD", ad="a"):
    """Una tienda con `dias` días de totales (10 de gasto, 30 de ventas, 1 pedido al día) y un anuncio de Meta con
    gasto cada día (la pestaña solo pinta Triple Whale con anuncios copiados)."""
    tid = triple_whale_tiendas.agregar("acme", "tw_llave_123", dominio, pais, moneda=moneda)  # llave-de-prueba
    triple_whale_tiendas.actualizar_tienda("acme", tid, ultima_sincronizacion=db.ahora())
    for n in range(dias):
        f = _hace(n)
        twdatos.reemplazar_tienda("acme", tid, f, f, [{"fecha": f, "gasto": 10, "ingresos": 30, "pedidos": 1}])
        twdatos.reemplazar_anuncios_canal("acme", tid, f, f, [{"canal": "facebook-ads", "ad_id": f"{ad}{pais}",
                                                               "fecha": f, "gasto": 5, "impresiones": 1000}])
    return tid


def _fila_por_pais(html, clave):
    """El <tr> de «Por país» de la entrada `clave`."""
    i = html.index(f'data-rend-entrada="{clave}"', html.index('id="rend-por-pais"'))
    return html[html.rindex("<tr", 0, i):html.index("</tr>", i)]


def _celdas(fila):
    return re.findall(r"<td[^>]*>(.*?)</td>", fila, flags=re.S)


# ---------------------------------------------------------------------------------------- R1 (A7) ---

def test_solo_tiendas_por_pais_arranca_donde_los_resultados_de_triple_whale(app, base_temporal):  # noqa: F811
    """Noruega tiene 10 días y Suecia 4: «Desde el inicio» de Triple Whale cuenta cada tienda desde su primer día, y
    «Por país» suma lo mismo (antes arrancaba en el primer día de Suecia y Noruega perdía 6 días)."""
    _tienda_con_dias("acme-no.myshopify.com", "NO", 10)
    _tienda_con_dias("acme-se.myshopify.com", "SE", 4)
    r = _ctx(dias=0)
    assert r["fuente"] == "tw" and r["actual"] is None and r["resumen"]["inicio_comun"] is None
    tarjetas = {t["clave"]: t["valor"] for t in r["tw"]["resultados"]["tarjetas"]}
    filas = r["resumen"]["por_pais"]
    assert sum(f["gasto"] for f in filas) == tarjetas["gasto"] == 140
    assert sum(f["ventas"] for f in filas) == tarjetas["ventas"] == 420
    html = _panel(app)
    assert 'id="rend-por-pais"' in html and "cuando empiezan los datos de todas tus fuentes" not in html


def test_en_una_mezcla_sigue_el_inicio_comun(base_temporal, meta_conectado):
    """R7 sin cambio cuando el alcance mezcla fuentes: la tienda tiene 5 días y Meta 20."""
    _sembrar()
    assert _ctx(dias=0)["resumen"]["inicio_comun"] == _hace(4)


# --------------------------------------------------------------------------------------- R2 y R3 ---

def _dos_tiendas_nok():
    _tienda_con_dias("acme-no.myshopify.com", "NO", 5, moneda="NOK")
    _tienda_con_dias("acme-se.myshopify.com", "SE", 5, moneda="NOK")


@pytest.mark.parametrize("con_tasas", [False, True])
def test_proyecto_en_nok_por_pais_va_en_nok(app, base_temporal, con_tasas):  # noqa: F811
    """Todas las filas comparten NOK: «Por país» va en NOK, con o sin tasas (no hace falta convertir nada)."""
    _dos_tiendas_nok()
    if con_tasas:
        for n in range(30):
            _tasa(_hace(n), 0.09, "NOK")
    r = _ctx(dias=0)
    assert r["resumen"]["moneda_pais"] == "NOK" and r["resumen"]["por_pais_sin_usd"] is False
    assert [(f["gasto_vista"], f["ventas_vista"], f["sin_usd"]) for f in r["resumen"]["por_pais"]] == [
        (50, 150, False), (50, 150, False)]
    html = _panel(app)
    celdas = _celdas(_fila_por_pais(html, "NO"))
    assert celdas[2] == "50 NOK" and celdas[3] == "150 NOK"
    assert "USD no disponible" not in html and "USD" not in html[html.index('id="rend-por-pais"'):
                                                                 html.index("</section>", html.index('id="rend-por-pais"'))]


def _nok_y_meta_sek(tasas_nok=True, cuenta_dkk=False):
    """Una tienda de Noruega en NOK y la cuenta de Suecia en SEK (5 días cada una), con tasas de SEK; las de NOK solo
    si `tasas_nok`. Con `cuenta_dkk`, una cuenta World Wide en DKK (sin tasas) cuyos anuncios llegan en la copia de la
    tienda: no suma en «Todas» pero sí tiene su fila en «Por país»."""
    tid = _tienda_con_dias("acme-no.myshopify.com", "NO", 5, moneda="NOK")
    elegidas = [{"id": "act_se", "name": "HappyFlops Sweden", "currency": "SEK", "pais": "SE"}]
    if cuenta_dkk:
        elegidas.append({"id": "act_ww", "name": "HappyFlops World Wide", "currency": "DKK", "pais": None})
    mcuentas.elegir("acme", elegidas)
    for n in range(5):
        f = _hace(n)
        mdatos.reemplazar_cuenta_dias("acme", "act_se", f, f, [_dia(f, 100, 150, compras=2)])
        _tasa(f, 0.1, "SEK")
        if tasas_nok:
            _tasa(f, 0.09, "NOK")
        if cuenta_dkk:
            mdatos.reemplazar_cuenta_dias("acme", "act_ww", f, f, [_dia(f, 40, 60, compras=1)])
            twdatos.reemplazar_anuncios_canal("acme", tid, f, f, [{"canal": "facebook-ads", "ad_id": "w1", "fecha": f,
                                                                   "gasto": 1, "cuenta_id": "act_ww"}])


def test_por_pais_con_monedas_distintas_va_en_usd_con_la_tienda_en_nok_convertida(meta_on):  # noqa: F811
    """Mutaciones 22 (la tienda en NOK sumada como si fuera USD) y 23 (la columna USD con la cifra local)."""
    _nok_y_meta_sek()
    with idiomas.en_idioma("es"):
        r = panel.contexto("acme", 0, hoy=HOY)
    assert r["resumen"]["moneda_pais"] == "USD" and r["resumen"]["por_pais_sin_usd"] is False
    no = next(f for f in r["resumen"]["por_pais"] if f["entrada"]["clave"] == "NO")
    assert (no["moneda"], no["gasto"], no["ventas"]) == ("NOK", 50, 150)
    assert round(no["gasto_usd"], 2) == round(no["gasto_vista"], 2) == 4.5          # 50 NOK × 0,09
    assert round(no["ventas_usd"], 2) == round(no["ventas_vista"], 2) == 13.5
    celdas = _celdas(_fila_por_pais(_panel(meta_on), "NO"))
    assert celdas[2].startswith("4,50 USD") and "50 NOK" in celdas[2]
    assert celdas[3].startswith("13,50 USD") and "150 NOK" in celdas[3]
    se = _celdas(_fila_por_pais(_panel(meta_on), "SE"))
    assert se[2].startswith("50 USD") and "500 SEK" in se[2]


def test_por_pais_sin_tasa_dice_usd_no_disponible_y_avisa(meta_on):  # noqa: F811
    """Resultados cuadra (tienda en NOK con tasa, Suecia en SEK con tasa), pero la cuenta World Wide en DKK no tiene
    tasa: su fila dice «USD no disponible» en vez de «—» y aparece el aviso de la página."""
    _nok_y_meta_sek(cuenta_dkk=True)
    with idiomas.en_idioma("es"):
        r = panel.contexto("acme", 0, hoy=HOY)
    assert r["resumen"]["usd_ok"] is True and r["resumen"]["resultados"] is not None
    ww = next(f for f in r["resumen"]["por_pais"] if f["entrada"]["clave"] == "cuenta:act_ww")
    assert ww["fuera_de_todas"] and ww["sin_usd"] and ww["gasto_vista"] is None
    assert r["resumen"]["por_pais_sin_usd"] is True
    html = _panel(meta_on)
    celdas = _celdas(_fila_por_pais(html, "cuenta:act_ww"))
    assert "USD no disponible" in celdas[2] and "200 DKK" in celdas[2]
    assert "USD no disponible para algunos días: elige un país para ver sus cifras." in html


def test_sin_tasa_de_la_tienda_la_fila_lo_dice(meta_on):  # noqa: F811
    _nok_y_meta_sek(tasas_nok=False)
    html = _panel(meta_on)
    celdas = _celdas(_fila_por_pais(html, "NO"))
    assert "USD no disponible" in celdas[2] and "50 NOK" in celdas[2]
    assert "USD no disponible para algunos días" in html


def _fila_tabla(html, marca):
    i = html.index(marca)
    return html[html.rindex("<tr", 0, i):html.index("</tr>", i)]


def test_una_campana_con_ventas_de_triple_whale_va_en_su_moneda_y_lo_dice(meta_on):  # noqa: F811
    """Mutaciones 24 (las cifras de una fila de Triple Whale en la moneda del presupuesto) y 25 (la etiqueta de fuente
    siempre «Meta»): la campaña y el conjunto que Triple Whale trae van en USD con «Triple Whale» y el presupuesto
    sigue en SEK; los que no trae van en SEK con «Meta»."""
    from tests.test_rendimiento_panel import _con_campanas_de_noruega
    _con_campanas_de_noruega()
    for n in range(3):                         # la parte Meta solo se pinta con días de cuenta copiados
        mdatos.reemplazar_cuenta_dias("acme", "act_no", _hace(n), _hace(n), [_dia(_hace(n), 15, 35, compras=2)])
    html = _panel(meta_on, "?entrada=NO&dias=7")
    cno = _celdas(_fila_tabla(html, "<strong>Campaña NO</strong>"))
    # Con Triple Whale en el proyecto la columna NVP (main, 2026-10-09) va después del ROAS: el costo por compra es la 9.ª.
    assert "Triple Whale" in cno[5] and "500 SEK" in cno[3] and cno[4] == "12 USD" and cno[8] == "2 USD"
    cno2 = _celdas(_fila_tabla(html, "<strong>cno2</strong>"))
    assert ">Meta<" in cno2[5] and cno2[4] == "15 SEK"
    sno = _celdas(_fila_tabla(html, "<strong>sno</strong>"))
    assert "Triple Whale" in sno[5] and sno[4] == "12 USD"
    sno2 = _celdas(_fila_tabla(html, "<strong>sno2</strong>"))
    assert ">Meta<" in sno2[5] and sno2[4] == "15 SEK"


def test_la_alerta_sin_compras_de_un_anuncio_de_meta_habla_de_meta(base_temporal, meta_conectado):
    """Mutación 26: las alertas de los anuncios de fuente Meta se arman con `origen="meta"`."""
    mcuentas.elegir("acme", [{"id": "act_se", "name": "HappyFlops Sweden", "currency": "SEK", "pais": "SE"}])
    for n in range(3):
        f = _hace(n)
        mdatos.reemplazar_cuenta_dias("acme", "act_se", f, f, [_dia(f, 60, 0, compras=0)])
        mdatos.reemplazar_anuncio_dias("acme", "act_se", f, f, [_ad(f, "se1", 60, 0, compras=0)])
    textos = [a["texto"] for a in _ctx(dias=0)["atencion"]]
    assert any(t.startswith("Meta no reporta ninguna compra") for t in textos)
    assert not any("Triple Whale" in t for t in textos)


def test_ver_mas_de_meta_en_todas_no_trae_los_anuncios_de_una_cuenta_cubierta(meta_on):  # noqa: F811
    """Mutación 27: la cuenta World Wide llega dentro de la tienda (R5); sus anuncios ya están en la parte de Triple
    Whale y la galería no los repite como anuncios de fuente Meta (desde E2 tarea 4, una sola galería: su ruta)."""
    _sembrar(cubierta_ww=True)
    for n in range(3):
        f = _hace(n)
        mdatos.reemplazar_anuncio_dias("acme", "act_ww", f, f, [_ad(f, "ww9", 80, 100, compras=1, campaign="cww")])
        mdatos.reemplazar_anuncio_dias("acme", "act_se", f, f, [_ad(f, "se9", 60, 90, compras=1, campaign="cse")])
    html = meta_on["c"].get("/cliente/acme/rendimiento/galeria?entera=1&entrada=").data.decode()
    assert 'id="tw-tarjeta-meta-facebook-ads-se9"' in html and "ww9" not in html
    panel_html = _panel(meta_on)
    galeria = panel_html[panel_html.index('id="tw-galeria"'):]
    assert "se9" in galeria and "ww9" not in galeria[:galeria.index("</section>")]


def test_sin_token_de_meta_no_se_leen_sus_cuentas(base_temporal, sin_meta):
    """Mutación 28: con cuentas elegidas pero sin conexión (sin token), el panel no las lee: ni entradas, ni
    campañas, ni anuncios de Meta."""
    _sembrar()
    r = _ctx(dias=0)
    assert r["hay_meta"] is False and r["meta"] is None
    assert [e["clave"] for e in r["entradas"]] == ["NO"] and r["entradas"][0]["cuentas"] == []


# ------------------------------------------------------------------------------------------------ R4 ---

def _anuncios_por_fuente(n):
    """`n` anuncios de Triple Whale en la tienda de Noruega y `n` de Meta en la cuenta de Suecia."""
    tid = triple_whale_tiendas.tiendas("acme")[0]["id"]
    for d in range(3):
        f = _hace(d)
        twdatos.reemplazar_anuncios_canal("acme", tid, f, f, [
            {"canal": "facebook-ads", "ad_id": f"t{i:02d}", "fecha": f, "anuncio": f"TW {i}", "gasto": 10 + i,
             "impresiones": 2000, "clics": 40, "vistas_3s": 600, "thruplays": 200} for i in range(n)])
        twdatos.reemplazar_anuncios_pixel("acme", tid, f, f, [
            {"canal": "facebook-ads", "ad_id": f"t{i:02d}", "fecha": f, "pedidos": i % 3, "ingresos": 40 * (i % 3)}
            for i in range(n)])
        mdatos.reemplazar_anuncio_dias("acme", "act_se", f, f, [
            _ad(f, f"m{i:02d}", 50 + i, 30 * (i % 4), compras=i % 4, adset=f"s{i % 5}", campaign=f"c{i % 3}")
            for i in range(n)])


def test_el_panel_hace_las_mismas_consultas_con_12_y_con_24_tarjetas_por_fuente(meta_on):  # noqa: F811
    from tests.test_escala import _Consultas
    _sembrar()
    _anuncios_por_fuente(12)
    # Desde E2 tarea 4, UNA galería con las dos fuentes: su primera página (12) y «Ver más».
    assert _panel(meta_on).count('<article class="tw-tarjeta') == 12
    with _Consultas() as doce:
        assert meta_on["c"].get("/cliente/acme/rendimiento/panel").status_code == 200
    _anuncios_por_fuente(24)
    with _Consultas() as veinticuatro:
        html = _panel(meta_on)
    assert html.count('<article class="tw-tarjeta') == 12 and html.count('id="tw-galeria"') == 1 and "data-tw-mas" in html
    assert doce.n == veinticuatro.n, (doce.n, veinticuatro.n)


# ------------------------------------------------------------------------------------------------ R5 ---

def test_una_sola_barra_para_las_copias_en_curso_del_alcance(meta_on):  # noqa: F811
    from tareas import meta_rendimiento as tareas_mr
    from tareas import triple_whale as tareas_tw
    _sembrar()
    assert tareas_tw.encolar_sync("acme") == 1
    assert tareas_mr.encolar_sync("acme") == 3
    html = _panel(meta_on)
    assert html.count("data-poll-job=") == 1 and 'id="rend-copias-acme"' in html
    tid = triple_whale_tiendas.tiendas("acme")[0]["id"]
    assert f'data-poll-job="acme__tw_sync__{tid}"' in html          # la primera copia viva
    assert "Trayendo 4 copias…" in html
    # Una entrada: solo sus copias (la tienda de Noruega y la cuenta de Noruega).
    una = _panel(meta_on, "?entrada=NO")
    assert una.count("data-poll-job=") == 1 and "Trayendo 2 copias…" in una
    suecia = _panel(meta_on, "?entrada=SE")
    assert 'data-poll-job="acme__meta_rend__act_se"' in suecia and "Trayendo 1 copia…" in suecia


# ------------------------------------------------------------------------------------------------ R6 ---

def test_atencion_junta_las_dos_fuentes_sin_quitar_repetidos_y_lo_alta_primero(monkeypatch):
    """Una alerta con cuenta (dos ganadores en Triple Whale, dos en Meta) no se esconde detrás de otra con el mismo
    texto, y una «alta» de los anuncios de Meta nunca queda debajo de «bien: N anuncios ganadores». (Hasta la
    integración con main la parte Meta traía también las recomendaciones propias de E2 tarea 6; se jubilaron: lo que hay
    que corregir en las cuentas de Meta es el Diagnóstico de main, que va en su propia sección.)"""
    tw = {"alertas": [{"nivel": "bien", "texto": "2 anuncios ganadores: úsalos como base para los próximos."},
                      {"nivel": "media", "texto": "Uno de Triple Whale"}]}
    meta = {"anuncios": {"ev": {"anuncios": []}}}
    monkeypatch.setattr(panel.evaluacion, "alertas", lambda ev, *a, origen="tw", **k: [
        {"nivel": "media", "texto": "Uno de Meta"},
        {"nivel": "alta", "texto": "El 60 % del gasto se fue en anuncios perdedores."},
        {"nivel": "bien", "texto": "2 anuncios ganadores: úsalos como base para los próximos."}])
    salida = panel._atencion(tw, meta)
    assert [(a["nivel"], a["texto"]) for a in salida] == [
        ("alta", "El 60 % del gasto se fue en anuncios perdedores."),
        ("media", "Uno de Triple Whale"), ("media", "Uno de Meta"),
        ("bien", "2 anuncios ganadores: úsalos como base para los próximos."),
        ("bien", "2 anuncios ganadores: úsalos como base para los próximos.")]


def test_atencion_con_una_evaluacion_bien_y_una_alerta_alta_de_meta(base_temporal, meta_conectado, monkeypatch):
    """Lo mismo de punta a punta: la línea «bien» de la evaluación de Triple Whale y una alerta «alta» de los anuncios
    de la cuenta de Meta: la alta va primero."""
    from tests.test_rutas_rendimiento import _con_anuncios
    _con_anuncios()
    original = panel.evaluacion.alertas

    def alertas(ev, *args, origen="tw", **kwargs):
        if origen == "meta":
            return [{"nivel": "alta", "texto": "El 60 % del gasto se fue en anuncios perdedores."}]
        return original(ev, *args, origen=origen, **kwargs)
    monkeypatch.setattr(panel.evaluacion, "alertas", alertas)
    atencion = _ctx(dias=0)["atencion"]
    niveles = [a["nivel"] for a in atencion]
    assert "bien" in niveles and niveles[0] == "alta"
    assert niveles == sorted(niveles, key={"alta": 0, "media": 1, "bien": 2}.get)


# ------------------------------------------------------------------------------------------------ R7 ---

def test_canal_sin_gasto_en_el_periodo_no_se_ofrece(app, base_temporal):  # noqa: F811
    """Pinterest tiene impresiones pero ningún gasto: su galería saldría vacía (R9 lo deja fuera)."""
    tid = _tienda_con_dias("acme.myshopify.com", None, 3)
    for n in range(3):
        f = _hace(n)
        twdatos.reemplazar_anuncios_canal("acme", tid, f, f, [
            {"canal": "facebook-ads", "ad_id": "aNone", "fecha": f, "gasto": 5, "impresiones": 1000},
            {"canal": "tiktok-ads", "ad_id": "t1", "fecha": f, "gasto": 3, "impresiones": 800},
            {"canal": "pinterest-ads", "ad_id": "p1", "fecha": f, "gasto": 0, "impresiones": 900}])
    assert twdatos.canales("acme", None, _hace(2), _hace(0)) == ["facebook-ads", "tiktok-ads"]
    html = _panel(app)
    selector = html[html.index('data-rend-param="canal"'):]
    selector = selector[:selector.index("</select>")]
    assert 'value="tiktok-ads"' in selector and 'value="pinterest-ads"' not in selector


# ------------------------------------------------------------------------------------------------ R8 ---

def test_sin_cuentas_el_estado_vacio_lleva_a_ajustes(meta_on):  # noqa: F811
    html = _panel(meta_on)
    assert html.count("Todavía no hay cuentas publicitarias elegidas") == 1
    assert "data-rend-ajustes" in html and "«Elegir cuentas de Meta»" in html


def test_la_ayuda_del_retorno_de_la_mezcla():
    from triple_whale import resultados
    assert resultados._AYUDAS["mixta"]["mer"] == "Las ventas entre todo el gasto en publicidad"
