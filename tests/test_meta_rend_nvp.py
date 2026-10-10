"""NVP en la pestaña «Meta» (spec 2026-10-09-nvp-visitantes-nuevos §4.2, pedido del cliente de HappyFlops): con
Triple Whale en el proyecto, el chip `chip-nvp` en el KPI y en cuentas, campañas, conjuntos y anuncios (también en
«Ver más»), con las SUMAS de visitantes de `tw_anuncio_dia`; sin Triple Whale, ni columna ni consultas de visitantes
y una línea que invita a conectarlo; los veredictos no cambian; y una consulta por nivel, nunca una por fila."""
from datetime import date, timedelta

import pytest
from sqlalchemy import event

import db
from meta_rendimiento import cuentas, datos, panel
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)

TOKEN = "tok-llave-de-prueba"   # llave-de-prueba
A, B = "act_1", "act_2"


def _hace(n):
    return (date.today() - timedelta(days=n)).isoformat()


def _dia(fecha, gasto, valor, compras=1):
    return dict(fecha=fecha, gasto=gasto, impresiones=10000, alcance=800, clics=200, clics_salida=100,
                compras=compras, valor=valor, vistas_3s=3000, thruplays=1000)


def _ad(fecha, ad, gasto, valor, compras=0, adset="s1", campaign="c1"):
    return dict(fecha=fecha, campaign_id=campaign, adset_id=adset, ad_id=ad, gasto=gasto, impresiones=5000,
                clics=100, clics_salida=60, compras=compras, valor=valor, vistas_3s=1500, thruplays=500,
                p25=900, p50=700, p75=500, p100=300)


def _tasas(moneda="SEK"):
    with db.conectar() as con:
        for d in range(0, 40):
            con.execute(db.tasa_cambio.insert().values(fecha=_hace(d), moneda=moneda, usd_por_unidad=0.1,
                                                       fuente="bce", creado_en=db.ahora()))


def _sembrar_meta(n_anuncios=2):
    """Norway (A) con la campaña c1 / conjunto s1 y sus anuncios «gana», «p00»…; Sweden (B) con «otra» en c2/s2."""
    cuentas.elegir("acme", [{"id": A, "name": "HappyFlops Norway", "currency": "SEK", "pais": "NO"},
                            {"id": B, "name": "HappyFlops Sweden", "currency": "SEK", "pais": "SE"}])
    f = _hace(2)
    datos.reemplazar_cuenta_dias("acme", A, f, f, [_dia(f, 400, 1000, compras=5)])
    datos.reemplazar_cuenta_dias("acme", B, f, f, [_dia(f, 200, 300, compras=2)])
    anuncios = [_ad(f, "gana", 100, 1000, compras=20)] + [_ad(f, f"p{i:02d}", 50 + i, 0)
                                                          for i in range(n_anuncios - 1)]
    datos.reemplazar_anuncio_dias("acme", A, f, f, anuncios)
    datos.reemplazar_anuncio_dias("acme", B, f, f, [_ad(f, "otra", 200, 300, compras=2, adset="s2", campaign="c2")])
    datos.guardar_objetos("acme", A, [
        {"nivel": "campana", "objeto_id": "c1", "nombre": "Campaña Otoño", "estado": "ACTIVE"},
        {"nivel": "conjunto", "objeto_id": "s1", "nombre": "Conjunto Mujeres", "estado": "ACTIVE"},
        {"nivel": "anuncio", "objeto_id": "gana", "nombre": "Video gana", "estado": "ACTIVE"},
        {"nivel": "anuncio", "objeto_id": "p00", "nombre": "Video p00", "estado": "ACTIVE"}])
    datos.guardar_objetos("acme", B, [{"nivel": "campana", "objeto_id": "c2", "nombre": "Campaña Suecia",
                                       "estado": "ACTIVE"},
                                      {"nivel": "conjunto", "objeto_id": "s2", "nombre": "Conjunto Suecia",
                                       "estado": "ACTIVE"}])
    _tasas()


def _sembrar_triple_whale(visitas, cliente="acme", dims=None, fecha=None):
    """Una tienda de Triple Whale (Noruega) y sus visitas del Pixel: `visitas` = [(ad_id, visitantes, nuevos)]. Las
    dimensiones (cuenta, campaña, conjunto) llegan en las filas del canal, como en la copia real."""
    import triple_whale_tiendas
    from triple_whale import datos as tw
    tid = triple_whale_tiendas.agregar(cliente, "k-prueba", "no.myshopify.com", pais="NO")
    f = fecha or _hace(2)
    dims = dims or {}
    tw.reemplazar_anuncios_canal(cliente, tid, f, f, [
        dict(canal="facebook-ads", ad_id=ad, fecha=f,
             **dims.get(ad, {"cuenta_id": A, "campana_id": "c1", "conjunto_id": "s1"})) for ad, _v, _n in visitas])
    tw.reemplazar_anuncios_pixel(cliente, tid, f, f, [
        dict(canal="facebook-ads", ad_id=ad, fecha=f, visitantes=v, visitantes_nuevos=n) for ad, v, n in visitas]
        # Otro canal del mismo anuncio no cuenta (el NVP de la pestaña Meta es el de facebook-ads).
        + [dict(canal="google-ads", ad_id="gana", fecha=f, visitantes=9999, visitantes_nuevos=9999)])
    return tid


@pytest.fixture()
def conectado(app, monkeypatch):  # noqa: F811
    """Meta conectado (solo métricas) para el panel; las respuestas nunca llevan el token."""
    monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar",
                        lambda c: {"token": TOKEN, "ad_account_id": A, "page_id": None})
    return app["c"]


def _fila(html, marca):
    """El primer <tr>…</tr> que contiene `marca`. Solo dentro de una fila: el «Diagnóstico» de E2 (2026-10-10) nombra
    campañas y conjuntos en sus tarjetas, antes de las tablas."""
    for trozo in html.split("<tr")[1:]:
        fila = trozo.split("</tr>")[0]
        if marca in fila:
            return "<tr" + fila
    raise ValueError(f"ninguna fila con {marca!r}")


def _kpi(html):
    i = html.index("meta-kpi-nvp")
    return html[i:html.index("</div>", i)]


# ---- con Triple Whale ---------------------------------------------------------------------------------------

def test_con_triple_whale_el_chip_en_el_kpi_y_en_cada_nivel(conectado):
    _sembrar_meta()
    # Norway: «gana» 80 de 100 (TOF) y «p00» 30 de 100 (BOF) -> cuenta, campaña y conjunto 110 de 200 = 55 % (MOF).
    _sembrar_triple_whale([("gana", 100, 80), ("p00", 100, 30)])
    html = conectado.get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert TOKEN not in html
    # KPI: la SUMA de las cuentas («Todas»), con el chip.
    kpi = _kpi(html)
    assert "Visitantes nuevos (NVP)" in kpi and "chip-nvp chip-nvp-mof" in kpi and "55&nbsp;%" in kpi
    # Solo Norway tiene Triple Whale: una línea lo dice, con su bandera y su nombre.
    linea = html[html.index("NVP de las cuentas con Triple Whale"):]
    linea = linea[:linea.index("</p>")]
    assert "Noruega" in linea and "🇳🇴" in linea and "Suecia" not in linea
    assert "Conecta Triple Whale" not in html
    # Una columna NVP en cada tabla: «Por cuenta», campañas, conjuntos y anuncios.
    assert html.count(">NVP</th>") == 4
    assert "55&nbsp;%" in _fila(html, f'data-meta-act="{A}"') and "MOF" in _fila(html, f'data-meta-act="{A}"')
    assert "chip-nvp-vacio" in _fila(html, f'data-meta-act="{B}"')          # Sweden: sin Triple Whale, «—»
    assert "55&nbsp;%" in _fila(html, "Campaña Otoño") and "chip-nvp-vacio" in _fila(html, "Campaña Suecia")
    assert "55&nbsp;%" in _fila(html, "Conjunto Mujeres") and "chip-nvp-vacio" in _fila(html, "Conjunto Suecia")
    gana, p00 = _fila(html, "Video gana"), _fila(html, "Video p00")
    assert "chip-nvp-tof" in gana and "80&nbsp;%" in gana
    assert "chip-nvp-bof" in p00 and "30&nbsp;%" in p00
    # Una cuenta sola: su KPI y sin la línea (todas las del alcance tienen datos), y Sweden sola dice «—».
    una = conectado.get(f"/cliente/acme/meta-rendimiento/panel?cuenta={A}").get_data(as_text=True)
    assert "55&nbsp;%" in _kpi(una) and "NVP de las cuentas con Triple Whale" not in una
    otra = conectado.get(f"/cliente/acme/meta-rendimiento/panel?cuenta={B}").get_data(as_text=True)
    assert "chip-nvp-vacio" in _kpi(otra) and "NVP de las cuentas con Triple Whale" not in otra


def test_pocos_visitantes_en_gris_y_cuenta_sin_prefijo_act(conectado):
    """Con menos de 50 visitantes el % va en gris y sin etapa; una tienda que guarda la cuenta sin «act_» suma igual."""
    _sembrar_meta()
    _sembrar_triple_whale([("gana", 10, 9)], dims={"gana": {"cuenta_id": "1", "campana_id": "c1",
                                                             "conjunto_id": "s1"}})
    html = conectado.get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert "chip-nvp-pocos" in _kpi(html) and "90&nbsp;%" in _kpi(html)
    assert "chip-nvp-pocos" in _fila(html, f'data-meta-act="{A}"')


def test_ver_mas_de_anuncios_y_conjuntos_lleva_la_columna(conectado, monkeypatch):
    _sembrar_meta(n_anuncios=30)
    _sembrar_triple_whale([("gana", 100, 80)] + [(f"p{i:02d}", 60, 30) for i in range(29)])
    html = conectado.get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert '<td colspan="10"><button type="button" class="btn-sm" data-meta-mas=' in html
    filas = conectado.get("/cliente/acme/meta-rendimiento/anuncios?dias=30&pagina=1").get_data(as_text=True)
    # 31 anuncios (30 de Norway + «otra» de Sweden): la segunda página trae 7, cada uno con su chip.
    assert filas.count("<tr data-veredicto=") == 7 and filas.count('class="chip-nvp chip-nvp-') == 7
    assert "chip-nvp-mof" in filas                                        # los p..: 30 de 60 = 50 %
    monkeypatch.setattr(panel, "POR_PAGINA", 1)
    html = conectado.get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
    assert '<td colspan="8"><button type="button" class="btn-sm" data-meta-mas=' in html
    mas = conectado.get("/cliente/acme/meta-rendimiento/conjuntos?dias=30&pagina=1").get_data(as_text=True)
    assert mas.count("<tr") == 1 and "chip-nvp-vacio" in mas               # el segundo conjunto (Sweden): «—»


def test_el_kpi_de_varias_cuentas_suma_visitantes_no_promedia_porcentajes(conectado):
    """Norway 90 de 100 (90 %) y Sweden 90 de 900 (10 %): la suma da 180 de 1 000 = 18 % (BOF); el promedio de
    porcentajes daría 50 % (revisión del NVP, mutación 2a)."""
    _sembrar_meta()
    _sembrar_triple_whale([("gana", 100, 90), ("otra", 900, 90)],
                          dims={"otra": {"cuenta_id": B, "campana_id": "c2", "conjunto_id": "s2"}})
    kpi = _kpi(conectado.get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True))
    assert "18&nbsp;%" in kpi and "chip-nvp-bof" in kpi and "50&nbsp;%" not in kpi


def test_el_nvp_respeta_el_periodo_de_la_pantalla(conectado):
    """Una visita de hace 20 días cuenta en 30 días y no en 7 (revisión del NVP, mutación 8)."""
    _sembrar_meta()
    _sembrar_triple_whale([("gana", 100, 80)], fecha=_hace(20))
    assert "80&nbsp;%" in _kpi(conectado.get("/cliente/acme/meta-rendimiento/panel?dias=30").get_data(as_text=True))
    siete = conectado.get("/cliente/acme/meta-rendimiento/panel?dias=7").get_data(as_text=True)
    assert "chip-nvp-vacio" in _kpi(siete) and "80&nbsp;%" not in _kpi(siete)


# ---- sin Triple Whale ---------------------------------------------------------------------------------------

def test_sin_triple_whale_ni_columna_ni_consultas_de_visitantes(conectado, monkeypatch):
    _sembrar_meta(n_anuncios=30)
    monkeypatch.setattr(panel.tw_datos, "visitantes_por",
                        lambda *a, **k: pytest.fail("sin Triple Whale no se piden visitantes"))
    consultas = []

    def contar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)
    event.listen(db.engine(), "before_cursor_execute", contar)
    try:
        html = conectado.get("/cliente/acme/meta-rendimiento/panel").get_data(as_text=True)
        filas = conectado.get("/cliente/acme/meta-rendimiento/anuncios?dias=30&pagina=1").get_data(as_text=True)
        conj = conectado.get("/cliente/acme/meta-rendimiento/conjuntos?dias=30&pagina=1").get_data(as_text=True)
    finally:
        event.remove(db.engine(), "before_cursor_execute", contar)
    assert not [q for q in consultas if "tw_anuncio_dia" in q]
    for texto in (html, filas, conj):
        assert "chip-nvp" not in texto and ">NVP</th>" not in texto
    assert "meta-kpi-nvp" not in html and "NVP de las cuentas con Triple Whale" not in html
    linea = html[html.index("Conecta Triple Whale"):]
    assert linea.startswith("Conecta Triple Whale para ver el % de visitantes nuevos (NVP).</a>")
    enlace = html[html.rindex("<a ", 0, html.index("Conecta Triple Whale")):html.index("Conecta Triple Whale")]
    assert 'href="#triplewhale"' in enlace and 'data-ir-tab="triplewhale"' in enlace
    assert '<td colspan="9"><button type="button" class="btn-sm" data-meta-mas=' in html


# ---- el NVP no decide nada y no cuesta una consulta por fila ------------------------------------------------

HOY = date(2026, 10, 8)


@pytest.fixture
def directo(base_temporal, monkeypatch):
    """`panel.contexto` sin Flask: Meta conectado, reglas por defecto y la clave para cifrar la llave de la tienda."""
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    monkeypatch.setattr(panel.meta_conexion, "cargar", lambda cliente: {"token": "tok-prueba", "page_id": None})
    monkeypatch.setattr(panel.meta_conexion, "modo", lambda cliente: "propia")
    monkeypatch.setattr(panel.proyectos, "reglas_defecto", lambda cliente: {})


FECHA = "2026-10-05"


def _sembrar_n(n_campanas, tasa=True):
    """`n_campanas` campañas en Norway, cada una con un conjunto y dos anuncios, y las visitas de cada anuncio en la
    copia de Triple Whale; Sweden con un anuncio y sin Triple Whale."""
    cuentas.elegir("hf", [{"id": A, "name": "HappyFlops Norway", "currency": "SEK", "pais": "NO"},
                          {"id": B, "name": "HappyFlops Sweden", "currency": "SEK", "pais": "SE"}])
    f = FECHA
    datos.reemplazar_cuenta_dias("hf", A, f, f, [_dia(f, 400, 1000, compras=5)])
    datos.reemplazar_cuenta_dias("hf", B, f, f, [_dia(f, 200, 300, compras=2)])
    anuncios = [_ad(f, f"a{i}-{j}", 10 + i + j, (i + j) * 30, compras=j, campaign=f"c{i}", adset=f"s{i}")
                for i in range(n_campanas) for j in range(2)]
    datos.reemplazar_anuncio_dias("hf", A, f, f, anuncios)
    datos.reemplazar_anuncio_dias("hf", B, f, f, [_ad(f, "otra", 200, 300, compras=2, adset="sx", campaign="cx")])
    if tasa:
        with db.conectar() as con:
            con.execute(db.tasa_cambio.insert().values(fecha=f, moneda="SEK", usd_por_unidad=0.1, fuente="bce",
                                                       creado_en=db.ahora()))
    return [(a["ad_id"], 60 + k, 20 + k) for k, a in enumerate(anuncios)], {
        a["ad_id"]: {"cuenta_id": A, "campana_id": a["campaign_id"], "conjunto_id": a["adset_id"]} for a in anuncios}


def _contar(fn):
    consultas = []

    def contar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)
    event.listen(db.engine(), "before_cursor_execute", contar)
    try:
        resultado = fn()
    finally:
        event.remove(db.engine(), "before_cursor_execute", contar)
    return resultado, consultas


def test_el_nvp_no_cambia_ningun_veredicto(directo, monkeypatch):
    visitas, dims = _sembrar_n(4)
    sin = panel.contexto("hf", hoy=HOY)
    assert sin["nvp_activo"] is False
    _sembrar_triple_whale(visitas, cliente="hf", dims=dims, fecha=FECHA)
    con = panel.contexto("hf", hoy=HOY)
    assert con["nvp_activo"] is True and con["nvp"]["visitantes"] == sum(v for _a, v, _n in visitas)
    clave = [(a["ad_id"], a["veredicto"], a["problemas"], a["fortalezas"], a["motivo"]) for a in sin["anuncios"]]
    assert [(a["ad_id"], a["veredicto"], a["problemas"], a["fortalezas"], a["motivo"]) for a in con["anuncios"]] == clave
    assert con["conteo"] == sin["conteo"] and con["meta_roas"] == sin["meta_roas"]
    # Cada anuncio trae sus visitas pegadas (solo para pintar).
    por_ad = {a: (v, n) for a, v, n in visitas}
    for a in con["anuncios"]:
        assert (a["visitantes"], a["visitantes_nuevos"]) == por_ad.get(a["ad_id"], (0, 0))


def test_una_consulta_por_nivel_nunca_por_fila(directo):
    visitas, dims = _sembrar_n(2)
    _ctx, sin_tw = _contar(lambda: panel.contexto("hf", hoy=HOY))
    _sembrar_triple_whale(visitas, cliente="hf", dims=dims, fecha=FECHA)
    ctx, pocas = _contar(lambda: panel.contexto("hf", hoy=HOY))
    assert len(ctx["campanas"]) == 3 and len(ctx["anuncios"]) == 5
    # Con Triple Whale: cuentas (que da el KPI), campañas, conjuntos y anuncios: 4 lecturas más.
    assert len(pocas) == len(sin_tw) + 4
    assert sum("tw_anuncio_dia" in q for q in pocas) == 4
    # Con seis veces más campañas, conjuntos y anuncios, las mismas consultas.
    with db.conectar() as con:
        con.execute(db.meta_anuncio_dia.delete())
        con.execute(db.tw_anuncio_dia.delete())
        con.execute(db.tw_tienda.delete())
        con.execute(db.triple_whale.delete())
    visitas, dims = _sembrar_n(12, tasa=False)
    _sembrar_triple_whale(visitas, cliente="hf", dims=dims, fecha=FECHA)
    ctx, muchas = _contar(lambda: panel.contexto("hf", hoy=HOY))
    assert len(ctx["campanas"]) == 13 and len(ctx["anuncios"]) == panel.POR_PAGINA
    assert len(muchas) == len(pocas), muchas
    # «Ver más»: una lectura de visitantes por página, también.
    _pag, consultas = _contar(lambda: panel.anuncios_pagina("hf", cuenta=None, pagina=0, hoy=HOY))
    assert sum("tw_anuncio_dia" in q for q in consultas) == 1
    _pag, consultas = _contar(lambda: panel.conjuntos_pagina("hf", cuenta=None, pagina=0, hoy=HOY))
    assert sum("tw_anuncio_dia" in q for q in consultas) == 1
