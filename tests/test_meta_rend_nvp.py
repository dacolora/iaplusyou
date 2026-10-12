"""NVP de las cuentas de Meta (spec 2026-10-09-nvp-visitantes-nuevos §4.2, pedido del cliente de HappyFlops). Main lo
pintó en la vieja pestaña «Meta» (KPI, «Por cuenta», campañas, conjuntos y anuncios); desde la integración con la
pestaña Rendimiento (2026-10-10, INT-1) vive allá: una línea con las SUMAS de las cuentas del alcance arriba de
«Campañas y conjuntos», la columna en campañas y conjuntos (también en su «Ver más») y la cifra en la tarjeta de un
anuncio de Meta de la galería única, todo de `tw_anuncio_dia`. Sin Triple Whale, ni columna ni consultas de visitantes
y una línea que invita a conectarlo (en «Ajustes»); los veredictos no cambian; y una consulta por nivel, nunca una por
fila. El KPI de la vieja pestaña y su «Por cuenta» no tienen lugar en Rendimiento (PND-281)."""
from datetime import date, timedelta

import pytest
from sqlalchemy import event

import db
from meta_rendimiento import cuentas, datos, panel
from pestana_rendimiento import galeria
from pestana_rendimiento import panel as rend_panel
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


def _sembrar_triple_whale(visitas, cliente="acme", dims=None, fecha=None, pais="NO"):
    """Una tienda de Triple Whale (Noruega) y sus visitas del Pixel: `visitas` = [(ad_id, visitantes, nuevos)]. Las
    dimensiones (cuenta, campaña, conjunto) llegan en las filas del canal, como en la copia real; un anuncio con
    `dims[ad] = None` solo llega por el Pixel (sin cuenta: su cuenta de Meta no queda «dentro» de la tienda, R5)."""
    import triple_whale_tiendas
    from triple_whale import datos as tw
    tid = triple_whale_tiendas.agregar(cliente, "k-prueba", f"{pais.lower()}.myshopify.com", pais=pais)
    f = fecha or _hace(2)
    dims = dims or {}
    canal = [ad for ad, _v, _n in visitas if dims.get(ad, True) is not None]     # dims None = solo el Pixel
    tw.reemplazar_anuncios_canal(cliente, tid, f, f, [
        dict(canal="facebook-ads", ad_id=ad, fecha=f,
             **dims.get(ad, {"cuenta_id": A, "campana_id": "c1", "conjunto_id": "s1"})) for ad in canal])
    tw.reemplazar_anuncios_pixel(cliente, tid, f, f, [
        dict(canal="facebook-ads", ad_id=ad, fecha=f, visitantes=v, visitantes_nuevos=n) for ad, v, n in visitas]
        # Otro canal del mismo anuncio no cuenta (el NVP de la pestaña Meta es el de facebook-ads).
        + [dict(canal="google-ads", ad_id="gana", fecha=f, visitantes=9999, visitantes_nuevos=9999)])
    return tid


RPANEL = "/cliente/acme/rendimiento/panel"


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


def _linea(html):
    """La línea del NVP de las cuentas de Meta, arriba de «Campañas y conjuntos» (el KPI de la vieja pestaña)."""
    i = html.index("rend-nvp-cuentas")
    return html[i:html.index("</p>", i)]


def _tarjeta(html, marca):
    """La tarjeta (<article>) de la galería que contiene `marca`."""
    i = html.index(marca)
    return html[html.rindex("<article", 0, i):html.index("</article>", i)]


# ---- con Triple Whale ---------------------------------------------------------------------------------------

def test_con_triple_whale_el_chip_en_la_linea_y_en_cada_nivel(conectado):
    _sembrar_meta()
    # Norway: «gana» 80 de 100 (TOF) y «p00» 30 de 100 (BOF) -> cuenta, campaña y conjunto 110 de 200 = 55 % (MOF).
    _sembrar_triple_whale([("gana", 100, 80), ("p00", 100, 30)])
    html = conectado.get(RPANEL).get_data(as_text=True)
    assert TOKEN not in html
    # La línea: la SUMA de las cuentas («Todas»), con el chip.
    linea = _linea(html)
    assert "Visitantes nuevos (NVP)" in linea and "chip-nvp chip-nvp-mof" in linea and "55&nbsp;%" in linea
    # Solo Norway tiene Triple Whale: la línea lo dice, con su bandera y su nombre.
    assert "NVP de las cuentas con Triple Whale" in linea and "Noruega" in linea and "🇳🇴" in linea
    assert "Suecia" not in linea and "Conecta Triple Whale" not in html
    # Una columna NVP en cada tabla de la estructura (campañas y conjuntos) y en «Ver como tabla» de Triple Whale.
    assert html.count(">NVP</th>") == 3
    assert "55&nbsp;%" in _fila(html, "Campaña Otoño") and "chip-nvp-vacio" in _fila(html, "Campaña Suecia")
    assert "55&nbsp;%" in _fila(html, "Conjunto Mujeres") and "chip-nvp-vacio" in _fila(html, "Conjunto Suecia")
    # La tarjeta de un anuncio de Meta (Sweden, fuente Meta) dice su NVP: sin visitas en la copia, «—».
    assert "chip-nvp-vacio" in _tarjeta(html, 'data-tarjeta-url="/cliente/acme/rendimiento/tarjeta/meta/facebook-ads/otra')
    # La entrada de Noruega sola: su línea, sin la nota (todas las cuentas del alcance tienen datos); Suecia sola, «—».
    una = conectado.get(RPANEL + "?entrada=NO").get_data(as_text=True)
    assert "55&nbsp;%" in _linea(una) and "NVP de las cuentas con Triple Whale" not in una
    otra = conectado.get(RPANEL + "?entrada=SE").get_data(as_text=True)
    assert "chip-nvp-vacio" in _linea(otra) and "NVP de las cuentas con Triple Whale" not in otra
    # La tarjeta NVP de «Resultados» es de Triple Whale (fuente tienda o anuncios): con Meta («SE») o mezcla («Todas»)
    # describiría solo una parte del alcance y no se pinta; en la entrada de la tienda («NO»), sí.
    assert "data-twr-nvp" not in otra and "data-twr-nvp" not in html and "data-twr-nvp" in una


def test_pocos_visitantes_en_gris_y_cuenta_sin_prefijo_act(conectado):
    """Con menos de 50 visitantes el % va en gris y sin etapa; una tienda que guarda la cuenta sin «act_» suma igual."""
    _sembrar_meta()
    _sembrar_triple_whale([("gana", 10, 9)], dims={"gana": {"cuenta_id": "1", "campana_id": "c1",
                                                             "conjunto_id": "s1"}})
    html = conectado.get(RPANEL).get_data(as_text=True)
    assert "chip-nvp-pocos" in _linea(html) and "90&nbsp;%" in _linea(html)


def test_ver_mas_de_conjuntos_lleva_la_columna(conectado, monkeypatch):
    _sembrar_meta()
    _sembrar_triple_whale([("gana", 100, 80)])
    monkeypatch.setattr(panel, "POR_PAGINA", 1)
    html = conectado.get(RPANEL).get_data(as_text=True)
    assert '<td colspan="8"><button type="button" class="btn-sm" data-meta-mas=' in html
    mas = conectado.get("/cliente/acme/rendimiento/conjuntos?pagina=1").get_data(as_text=True)
    # El segundo conjunto por gasto (Norway: 100 de «gana» contra los 200 de Sweden), con su chip: 80 de 100.
    assert mas.count("<tr") == 1 and "Conjunto Mujeres" in mas and "chip-nvp-tof" in mas and "80&nbsp;%" in mas


def test_la_tarjeta_de_un_anuncio_de_meta_lleva_su_nvp(conectado):
    """Un anuncio de una cuenta sin tienda cuyas visitas trae el Pixel de Triple Whale (sin cuenta en la fila: su cuenta
    sigue siendo de fuente Meta, R5) muestra su NVP en la tarjeta de la galería, también en la tarjeta sola."""
    _sembrar_meta()
    _sembrar_triple_whale([("gana", 100, 80), ("otra", 100, 20)], dims={"otra": None})
    html = conectado.get(RPANEL).get_data(as_text=True)
    url = "/cliente/acme/rendimiento/tarjeta/meta/facebook-ads/otra"
    tarjeta = _tarjeta(html, f'data-tarjeta-url="{url}')
    assert "Visitantes nuevos (NVP)" in tarjeta and "chip-nvp-bof" in tarjeta and "20&nbsp;%" in tarjeta
    sola = conectado.get(url + "?entrada=&dias=0").get_data(as_text=True)
    assert "chip-nvp-bof" in sola and "20&nbsp;%" in sola


def test_la_linea_de_varias_cuentas_suma_visitantes_no_promedia_porcentajes(conectado):
    """Norway 90 de 100 (90 %) y Sweden 90 de 900 (10 %): la suma da 180 de 1 000 = 18 % (BOF); el promedio de
    porcentajes daría 50 % (revisión del NVP, mutación 2a)."""
    _sembrar_meta()
    _sembrar_triple_whale([("gana", 100, 90), ("otra", 900, 90)],
                          dims={"otra": {"cuenta_id": B, "campana_id": "c2", "conjunto_id": "s2"}})
    linea = _linea(conectado.get(RPANEL).get_data(as_text=True))
    assert "18&nbsp;%" in linea and "chip-nvp-bof" in linea and "50&nbsp;%" not in linea


def test_el_nvp_respeta_el_periodo_de_la_pantalla(conectado):
    """Una visita de hace 20 días cuenta en 30 días y no en 7 (revisión del NVP, mutación 8)."""
    _sembrar_meta()
    _sembrar_triple_whale([("gana", 100, 80)], fecha=_hace(20))
    assert "80&nbsp;%" in _linea(conectado.get(RPANEL + "?dias=30").get_data(as_text=True))
    siete = conectado.get(RPANEL + "?dias=7").get_data(as_text=True)
    assert "chip-nvp-vacio" in _linea(siete) and "80&nbsp;%" not in _linea(siete)


# ---- sin Triple Whale ---------------------------------------------------------------------------------------

def test_sin_triple_whale_ni_columna_ni_consultas_de_visitantes(conectado, monkeypatch):
    _sembrar_meta(n_anuncios=30)
    from triple_whale import datos as twdatos
    monkeypatch.setattr(twdatos, "visitantes_por", lambda *a, **k: pytest.fail("sin Triple Whale no se piden visitantes"))
    monkeypatch.setattr(panel, "POR_PAGINA", 1)
    consultas = []

    def contar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)
    event.listen(db.engine(), "before_cursor_execute", contar)
    try:
        html = conectado.get(RPANEL).get_data(as_text=True)
        tarjetas = conectado.get("/cliente/acme/rendimiento/galeria?pagina=2").get_data(as_text=True)
        conj = conectado.get("/cliente/acme/rendimiento/conjuntos?pagina=1").get_data(as_text=True)
    finally:
        event.remove(db.engine(), "before_cursor_execute", contar)
    assert not [q for q in consultas if "tw_anuncio_dia" in q]
    for texto in (html, tarjetas, conj):
        assert "chip-nvp" not in texto and ">NVP</th>" not in texto and "Visitantes nuevos (NVP)" not in texto
    assert "rend-nvp-cuentas" not in html and "NVP de las cuentas con Triple Whale" not in html
    linea = html[html.index("Conecta Triple Whale"):]
    assert linea.startswith("Conecta Triple Whale para ver el % de visitantes nuevos (NVP).</a>")
    enlace = html[html.rindex("<a ", 0, html.index("Conecta Triple Whale")):html.index("Conecta Triple Whale")]
    assert 'href="#rend-ajustes"' in enlace and "data-rend-ajustes" in enlace          # R1: nunca #triplewhale
    assert '<td colspan="7"><button type="button" class="btn-sm" data-meta-mas=' in html


# ---- el NVP no decide nada y no cuesta una consulta por fila ------------------------------------------------

HOY = date(2026, 10, 8)


@pytest.fixture
def directo(base_temporal, monkeypatch):
    """Sin Flask: Meta conectado, reglas por defecto y la clave para cifrar la llave de la tienda."""
    import meta_conexion
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    monkeypatch.setattr(meta_conexion, "cargar", lambda cliente: {"token": "tok-prueba", "page_id": None})
    monkeypatch.setattr(meta_conexion, "modo", lambda cliente: "propia")
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


def test_el_nvp_no_cambia_ningun_veredicto(directo):
    """Las visitas se pegan DESPUÉS de evaluar: las tarjetas de Meta de la galería tienen los mismos veredictos con y
    sin Triple Whale. La tienda es de otro país (Dinamarca) y las visitas llegan solo por el Pixel: así ninguna cuenta
    queda «dentro» de la tienda (R3, R5) y la galería es la misma."""
    visitas, _dims = _sembrar_n(4)
    sin = rend_panel.contexto("hf", hoy=HOY)["galeria"]["tarjetas"]
    assert len(sin) == 9 and all(a.get("sin_nvp") for a in sin)
    _sembrar_triple_whale(visitas, cliente="hf", dims={a: None for a, _v, _n in visitas}, fecha=FECHA, pais="DK")
    con = rend_panel.contexto("hf", hoy=HOY)["galeria"]["tarjetas"]
    clave = [(a["ad_id"], a["veredicto"], a["problemas"], a["fortalezas"], a["motivo"]) for a in sin]
    assert [(a["ad_id"], a["veredicto"], a["problemas"], a["fortalezas"], a["motivo"]) for a in con] == clave
    por_ad = {a: (v, n) for a, v, n in visitas}
    for a in con:
        assert not a["sin_nvp"]
        assert (a["m"]["visitantes"], a["m"]["visitantes_nuevos"]) == por_ad.get(a["ad_id"], (0, 0))


def test_una_consulta_por_nivel_nunca_por_fila(directo):
    """`panel.nvp_estructura`: campañas, conjuntos y cuentas, una lectura cada una, crezcan o no las filas; sin Triple
    Whale, ninguna. La tarjeta de Meta, una por página de la galería (`galeria._nvp_meta`)."""
    visitas, dims = _sembrar_n(2)
    _sembrar_triple_whale(visitas, cliente="hf", dims=dims, fecha=FECHA)
    por_id = {c["ad_account_id"]: c for c in panel.lista("hf")}
    en = list(por_id.values())

    def leer():
        es = panel.estructura("hf", [A, B], FECHA, FECHA, 30, por_id)
        nvp = panel.nvp_estructura("hf", es["campanas"], es["conjuntos"], en, FECHA, FECHA, True)
        return es, nvp
    (es, nvp), pocas = _contar(leer)
    assert len(es["campanas"]) == 3 and nvp["nvp_activo"] is True
    assert sum("tw_anuncio_dia" in q for q in pocas) == 3
    assert nvp["nvp"]["visitantes"] == sum(v for _a, v, _n in visitas)
    _x, ninguna = _contar(lambda: panel.nvp_estructura("hf", es["campanas"], es["conjuntos"], en, FECHA, FECHA, False))
    assert ninguna == []
    with db.conectar() as con:
        con.execute(db.meta_anuncio_dia.delete())
        con.execute(db.tw_anuncio_dia.delete())
        con.execute(db.tw_tienda.delete())
        con.execute(db.triple_whale.delete())
    visitas, dims = _sembrar_n(12, tasa=False)
    _sembrar_triple_whale(visitas, cliente="hf", dims=dims, fecha=FECHA)
    (es, nvp), muchas = _contar(leer)
    assert len(es["campanas"]) == 13 and len(muchas) == len(pocas)
    # La galería: una lectura de visitantes para las tarjetas de Meta de la página, sean cuantas sean.
    tarjetas = [dict(a, m=dict(a["m"])) for a in panel.anuncios_evaluados("hf", [B], FECHA, FECHA, HOY, por_id)["anuncios"]]
    _x, consultas = _contar(lambda: galeria._nvp_meta("hf", tarjetas, {"desde": FECHA, "hasta": FECHA}, True))
    assert sum("tw_anuncio_dia" in q for q in consultas) == 1
