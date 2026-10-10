"""Rendimiento E2 (4/7): una sola galería con los anuncios de las dos fuentes y un solo lote (spec 2026-10-09 §5 y A1;
PND-196). Una tienda de Triple Whale en Noruega (USD) y una cuenta de Meta en Suecia (SEK, 0,1 USD por corona): sus
anuncios van en UNA galería ordenada por gasto en USD, el lote los mezcla, cada uno se cobra con el alcance de SU
fuente y lo pagado conserva sus garantías (precio a la vista, nada dos veces, sin saldo no se crea nada)."""
import re
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

import db
import proyectos
import triple_whale_tiendas
from meta_rendimiento import cuentas as mcuentas
from meta_rendimiento import datos as mdatos
from pestana_rendimiento import galeria
from pestana_rendimiento import panel as rend_panel
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_meta_rendimiento import _ad, _dia, _tasa
from tests.test_rutas_triple_whale import _tareas
from triple_whale import datos as twdatos

TOKEN = "t-llave-de-prueba"   # llave-de-prueba
SE = "act_se"
POST = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture(autouse=True)
def _aislado(tmp_path, monkeypatch):
    """Preferencias y aprendizajes viven en clientes/<c>/proyecto.json: que las pruebas no escriban en el repo."""
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))


@pytest.fixture()
def mixto(app, monkeypatch):  # noqa: F811
    """Meta conectado (solo métricas) además de lo que el proyecto tenga de Triple Whale."""
    monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar", lambda c: {"token": TOKEN, "page_id": None})
    with app["dashboard"].app.test_request_context():
        yield app


def _hace(n):
    return (date.today() - timedelta(days=n)).isoformat()


def _sembrar(tw=(("t1", 30), ("t2", 10)), meta=(("m1", 200), ("m2", 500)), con_tasa=True, poco=True,
             moneda_meta="SEK"):
    """Cinco días. Triple Whale en USD (gasto diario por anuncio) y Meta en SEK (×0,1 = USD). Con `poco`, un anuncio
    de muy pocos datos en cada fuente (`tn`, `mn`). Por USD: m2 (250) > t1 (150) > m1 (100) > t2 (50); por gasto
    nominal sería m2, m1, t1, t2."""
    tid = triple_whale_tiendas.agregar("acme", "tw_llave_123", "acme-no.myshopify.com", "NO", moneda="USD")  # llave-de-prueba
    triple_whale_tiendas.actualizar_tienda("acme", tid, ultima_sincronizacion=db.ahora())
    mcuentas.elegir("acme", [{"id": SE, "name": "HappyFlops Sweden", "currency": moneda_meta, "pais": "SE"}])
    for n in range(5):
        f = _hace(n)
        mdatos.reemplazar_cuenta_dias("acme", SE, f, f, [_dia(f, 700, 1400, compras=3)])
        if con_tasa:
            _tasa(f, 0.1, moneda_meta)
    _anuncios(tid, tw, meta, poco)
    return tid


def _anuncios(tid, tw, meta, poco=False):
    """Reemplaza los anuncios de las dos fuentes (cinco días, los mismos de `_sembrar`)."""
    canal, pixel, tienda = [], [], []
    for n in range(5):
        f = _hace(n)
        for ad, gasto in tw:
            canal.append({"canal": "facebook-ads", "ad_id": ad, "fecha": f, "anuncio": f"Anuncio {ad}", "gasto": gasto,
                          "impresiones": 3000, "clics": 60, "vistas_3s": 900, "thruplays": 300})
            pixel.append({"canal": "facebook-ads", "ad_id": ad, "fecha": f, "pedidos": 1, "ingresos": gasto * 2})
        if poco:
            canal.append({"canal": "facebook-ads", "ad_id": "tn", "fecha": f, "anuncio": "Anuncio tn", "gasto": 1,
                          "impresiones": 20})
        tienda.append({"fecha": f, "gasto": 50, "ingresos": 150, "pedidos": 3})
        filas_meta = [_ad(f, ad, gasto, gasto * 2, compras=1) for ad, gasto in meta]
        if poco:
            filas_meta.append(dict(_ad(f, "mn", 1, 0), impresiones=20))
        mdatos.reemplazar_anuncio_dias("acme", SE, f, f, filas_meta)
    twdatos.reemplazar_anuncios_canal("acme", tid, _hace(4), _hace(0), canal)
    twdatos.reemplazar_anuncios_pixel("acme", tid, _hace(4), _hace(0), pixel)
    twdatos.reemplazar_tienda("acme", tid, _hace(4), _hace(0), tienda)


def _alcances(entrada="", dias=0, canal=None):
    return rend_panel.alcances("acme", dias, entrada, canal)


def _armar(veredicto="", pagina=1, **k):
    al = _alcances(**k)
    return galeria.armar("acme", al["tw"], al["meta"], veredicto, pagina)


def _orden(g):
    return [(a["fuente"], a["ad_id"]) for a in g["tarjetas"]]


def _jobs():
    return sorted(t["job_id"] for t in _tareas("tw_analizar_anuncio"))


def _filas():
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.tw_analisis).order_by(db.tw_analisis.c.id))]


def _panel(app, q=""):  # noqa: F811
    return app["c"].get("/cliente/acme/rendimiento/panel" + q).data.decode()


def _claves_del_lote(html):
    return re.findall(r'<input type="hidden" name="clave" value="([^"]+)">', html)


def _lote(app, claves, **extra):  # noqa: F811
    data = dict({"entrada": "", "dias": "0", "canal": "", "veredicto": "", "clave": claves}, **extra)
    return app["c"].post("/cliente/acme/rendimiento/analizar-lote", data=data, headers=POST, follow_redirects=True)


def _analizar(app, fuente, ad, json=True, entrada="", **headers):  # noqa: F811
    h = dict(POST, **headers)
    if json:
        h["Accept"] = "application/json"
    return app["c"].post(f"/cliente/acme/rendimiento/anuncio/{fuente}/facebook-ads/{ad}/analizar",
                         data={"entrada": entrada, "dias": "0", "canal": ""}, headers=h)


# ------------------------------------------------------------------------------------- el orden (PND-196) ---

def test_la_galeria_ordena_por_gasto_en_usd_con_dos_monedas(mixto):
    _sembrar()
    g = _armar()
    assert _orden(g) == [("meta", "m2"), ("tw", "t1"), ("meta", "m1"), ("tw", "t2")]       # nominal: m2, m1, t1, t2
    usd = {a["ad_id"]: a["gasto_usd"] for a in g["tarjetas"]}
    assert usd["m2"] == pytest.approx(250) and usd["t1"] == pytest.approx(150) and usd["m1"] == pytest.approx(100)
    monedas = {a["ad_id"]: (a["fuente"], a["moneda"]) for a in g["tarjetas"]}
    assert monedas["m2"] == ("meta", "SEK") and monedas["t1"] == ("tw", "USD")
    # Lo mismo en el panel: la tarjeta de m2 va antes que la de t1 y la de t1 antes que la de m1.
    html = _panel(mixto)
    pos = [html.index(f'id="tw-tarjeta-{k}"') for k in ("meta-facebook-ads-m2", "facebook-ads-t1",
                                                         "meta-facebook-ads-m1", "facebook-ads-t2")]
    assert pos == sorted(pos)


def test_sin_tasa_los_de_esa_moneda_van_al_final_en_su_orden_nominal(mixto):
    """R6: sin tasa no se inventa una; esos anuncios no se mezclan con los que sí tienen USD."""
    _sembrar(con_tasa=False)
    g = _armar()
    assert _orden(g) == [("tw", "t1"), ("tw", "t2"), ("meta", "m2"), ("meta", "m1")]
    assert [a["gasto_usd"] for a in g["tarjetas"]][2:] == [None, None]


def test_una_entrada_sola_trae_solo_su_fuente(mixto):
    _sembrar()
    assert {a["fuente"] for a in _armar(entrada="SE")["tarjetas"]} == {"meta"}
    assert {a["fuente"] for a in _armar(entrada="NO")["tarjetas"]} == {"tw"}


# ------------------------------------------------------------------------------------ filtros y conteo ---

def test_filtros_y_conteo_mezclados(mixto):
    _sembrar()
    g = _armar()
    assert g["n_anuncios"] == 6 and g["total"] == 4 and g["conteo_filtros"][""] == 4
    assert g["conteo_filtros"]["sin_datos"] == 2 and g["hay_meta"] is True
    al = _alcances()
    todos = al["tw"]["ev"]["anuncios"] + al["meta"]["ev"]["anuncios"]
    for f in ("ganador", "prometedor", "en_prueba", "perdedor"):
        assert g["conteo_filtros"][f] == sum(1 for a in todos if a["veredicto"] == f), f
    pocos = _armar(veredicto="sin_datos")
    assert sorted(_orden(pocos)) == [("meta", "mn"), ("tw", "tn")]
    # La ruta con un filtro trae el bloque entero de ese filtro, con tarjetas de las dos fuentes.
    html = mixto["c"].get("/cliente/acme/rendimiento/galeria?entera=1&veredicto=sin_datos").data.decode()
    assert html.lstrip().startswith('<div class="tw-galeria-bloque"')
    assert 'id="tw-tarjeta-facebook-ads-tn"' in html and 'id="tw-tarjeta-meta-facebook-ads-mn"' in html
    assert "tw-analizar-lote" not in html                                   # muy pocos datos: nada que cobrar
    assert re.search(r'class="chip activo" data-tw-galeria-filtro="sin_datos"', html)


def test_ver_mas_trae_la_segunda_pagina_mezclada(mixto):
    _sembrar(tw=[(f"t{i:02d}", 10 + 2 * i) for i in range(8)], meta=[(f"m{i:02d}", 100 + 20 * i + 5) for i in range(8)],
             poco=False)
    g1, g2 = _armar(), _armar(pagina=2)
    assert len(g1["tarjetas"]) == 12 and g1["hay_mas"] and len(g2["tarjetas"]) == 4 and not g2["hay_mas"]
    assert not {clave for clave in _orden(g1)} & {clave for clave in _orden(g2)}
    p2 = mixto["c"].get("/cliente/acme/rendimiento/galeria?pagina=2").data.decode()
    assert p2.count('<article class="tw-tarjeta') == 4 and "tw-galeria-bloque" not in p2
    assert "tw-analizar-lote" not in p2 and "Ver más" not in p2


# ---------------------------------------------------------------------------------------- el lote ---

def test_el_lote_mezcla_las_dos_fuentes_y_suma_sus_precios(mixto):
    _sembrar()
    g = _armar()
    assert g["lote"]["claves"] == ["meta:facebook-ads:m2", "tw:facebook-ads:t1", "meta:facebook-ads:m1",
                                   "tw:facebook-ads:t2"]
    assert g["lote"]["elegibles"] == set(g["lote"]["claves"])
    precios = {a["ad_id"]: a["precio_analisis"]["usd"] for a in g["tarjetas"]}
    assert g["lote"]["precio"]["usd"] == pytest.approx(sum(precios.values()), abs=1e-4)
    html = _panel(mixto)
    assert _claves_del_lote(html) == g["lote"]["claves"]
    assert f"Analizar los 4 que más gastaron · {g['lote']['precio']['texto']}" in html
    assert 'action="/cliente/acme/rendimiento/analizar-lote"' in html


def test_el_lote_cobra_solo_lo_confirmado_y_elegible_de_cada_fuente(mixto):
    tid = _sembrar()
    falsas = ["meta:facebook-ads:t1",           # un anuncio de Triple Whale con la fuente de Meta: no está en ese alcance
              "tw:facebook-ads:m2",             # y al revés
              "meta:facebook-ads:mn", "tw:facebook-ads:tn",            # muy pocos datos: nunca se cobran
              "x:facebook-ads:m2", "facebook-ads:m2", "meta:facebook-ads:", ":facebook-ads:m2", "meta:a:b:c", ""]
    r = _lote(mixto, falsas + ["meta:facebook-ads:m1", "tw:facebook-ads:t2", "meta:facebook-ads:m1"])
    assert _jobs() == ["acme__tw_anuncio__facebook-ads__m1", "acme__tw_anuncio__facebook-ads__t2"]
    assert "Analizando 2 anuncios con IA" in r.data.decode()
    assert all(t["max_intentos"] == 1 for t in _tareas("tw_analizar_anuncio"))
    por_ad = {f["ad_id"]: f for f in _filas()}
    assert set(por_ad) == {"m1", "t2"}
    # Cada uno con el alcance de SU fuente (traspaso de la tarea 3): la foto dice de dónde salen los números.
    m1, t2 = por_ad["m1"], por_ad["t2"]
    assert m1["foto"]["fuente"] == "meta" and m1["foto"]["ad_account_id"] == SE and m1["moneda"] == "SEK"
    assert m1["tienda_id"] is None and m1["foto"]["metodo"] == 2 and m1["foto"]["cuenta"]["modelo"] == "Pixel de Meta"
    assert t2["foto"]["fuente"] == "triple_whale" and "ad_account_id" not in t2["foto"] and t2["moneda"] == "USD"
    assert t2["tienda_id"] == tid and t2["foto"]["metodo"] == 2


def test_un_segundo_envio_del_mismo_lote_no_cobra(mixto):
    _sembrar()
    claves = _claves_del_lote(_panel(mixto))
    assert len(claves) == 4
    _lote(mixto, claves)
    assert len(_jobs()) == 4 and len(_filas()) == 4
    r = _lote(mixto, claves)                                 # la pestaña vieja, «atrás» o un doble clic
    assert len(_jobs()) == 4 and len(_filas()) == 4
    assert "No quedó ningún anuncio por analizar" in r.data.decode()


def test_el_lote_solo_ofrece_los_que_su_tarjeta_ofrece(mixto):
    """Uno con su análisis en curso (o fresco) no entra al lote ni a lo elegible, sea de la fuente que sea."""
    from tareas import triple_whale as tareas_tw
    _sembrar()
    assert _analizar(mixto, "meta", "m2").get_json()["ok"]                # m2 queda con su tarea viva
    al = _alcances()
    t1 = next(a for a in al["tw"]["ev"]["anuncios"] if a["ad_id"] == "t1")
    aid = twdatos.crear_analisis("acme", al["tw"]["tienda_id"], "facebook-ads", "t1", al["tw"]["desde"],
                                 al["tw"]["hasta"], "USD", {"metodo": 2, "veredicto": t1["veredicto"],
                                                            "m": {"gasto": t1["m"]["gasto"]}})
    twdatos.actualizar_analisis(aid, estado="lista", resultado={"frase": "x"})      # t1 con uno fresco de este alcance
    assert tareas_tw.job_id_analisis("acme", "facebook-ads", "m2") in tareas_tw.analisis_vivos("acme")
    g = _armar()
    assert g["lote"]["claves"] == ["meta:facebook-ads:m1", "tw:facebook-ads:t2"]
    assert g["lote"]["elegibles"] == {"meta:facebook-ads:m1", "tw:facebook-ads:t2"}
    assert "Analizar los 2 que más gastaron" in _panel(mixto)


def test_meta_reporta_nunca_va_en_una_tarjeta_de_meta(mixto):
    """R12 es de Triple Whale: aunque un anuncio de Meta trajera la cifra, su tarjeta no la pinta."""
    from flask import render_template
    _sembrar()
    al = _alcances()
    a = next(x for x in al["meta"]["ev"]["anuncios"] if x["ad_id"] == "m2")
    galeria.tarjeta("acme", "meta", al["meta"], a)
    a["m"]["roas_canal"] = 2.5
    html = render_template("_tw_galeria_fragmento.html", modo="tarjeta", a=a, cliente="acme", params=al["params"],
                           params_tw={}, textos=rend_panel.etiquetas())
    assert 'data-fuente="meta"' in html and "Meta reporta" not in html
    t1 = next(x for x in al["tw"]["ev"]["anuncios"] if x["ad_id"] == "t1")
    galeria.tarjeta("acme", "tw", al["tw"], t1)
    t1["m"]["roas_canal"] = 2.5
    html = render_template("_tw_galeria_fragmento.html", modo="tarjeta", a=t1, cliente="acme", params=al["params"],
                           params_tw=al["params_tw"], textos=rend_panel.etiquetas())
    assert "Meta reporta" in html


def test_el_tope_del_lote_es_entre_las_dos_fuentes(mixto):
    """B6: diez entre las dos, no diez por fuente (el recorte va ANTES de separar)."""
    _sembrar(tw=[(f"t{i:02d}", 10 + i) for i in range(8)], meta=[(f"m{i:02d}", 100 + 10 * i) for i in range(8)],
             poco=False)
    assert _armar()["lote"]["n"] == 10
    todas = [f"meta:facebook-ads:m{i:02d}" for i in range(8)] + [f"tw:facebook-ads:t{i:02d}" for i in range(8)]
    _lote(mixto, todas)
    assert len(_jobs()) == 10 and len(_filas()) == 10
    assert sum(1 for j in _jobs() if "__m" in j) == 8                      # las primeras diez confirmadas


def test_claves_confirmadas():
    valores = ["meta:facebook-ads:m1"] * 3000 + ["tw:facebook-ads:m1", "x:facebook-ads:1", "meta:facebook-ads:a/b",
                                                 "meta:", "meta:facebook-ads:p1\n"] + \
        [f"tw:tiktok-ads:{i}" for i in range(30)]
    claves = galeria.claves_confirmadas(valores)
    assert claves[:2] == [("meta", "facebook-ads", "m1"), ("tw", "facebook-ads", "m1")]
    assert len(claves) == 10 == len(set(claves)) and claves[2:] == [("tw", "tiktok-ads", str(i)) for i in range(8)]
    assert galeria.claves_confirmadas(["tw:a:1", "tw:a:1", "meta:a:1"], tope=5) == [("tw", "a", "1"), ("meta", "a", "1")]


# --------------------------------------------------------------------------------------- sin saldo ---

def _cobra(milesimas=0):
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    if milesimas:
        with db.conectar() as con:
            libro.acreditar(con, "acme", "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")
    return libro


def _precio(libro, ad):
    from triple_whale import panel
    usd = panel.precio_analisis(twdatos.creativos("acme", [("facebook-ads", ad)]).get(("facebook-ads", ad)))["usd"]
    return libro.precio_milesimas(usd, libro.margen_precio("acme"))


def test_sin_saldo_el_lote_no_crea_nada(mixto):
    _sembrar()
    claves = _claves_del_lote(_panel(mixto))
    _cobra()
    html = _lote(mixto, claves).data.decode()
    assert _jobs() == [] and _filas() == [] and "Saldo insuficiente" in html and "Recargar saldo" in html


def test_sin_saldo_para_todo_el_lote_para_en_la_primera_fuente_sin_saldo(mixto):
    """Alcanza para dos: salen los dos de Meta (la fuente del anuncio de más gasto va primero) y Triple Whale no se
    pide; el aviso dice cuántos salieron."""
    _sembrar()
    claves = _claves_del_lote(_panel(mixto))
    libro = _cobra()
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", _precio(libro, "m2") + _precio(libro, "m1"), "ajuste", usuario="admin",
                        detalle="prueba")
    html = _lote(mixto, claves).data.decode()
    assert _jobs() == ["acme__tw_anuncio__facebook-ads__m1", "acme__tw_anuncio__facebook-ads__m2"]
    assert len(_filas()) == 2 and libro.disponible("acme") == 0
    assert "Analizando 2 anuncios con IA" in html and "Saldo insuficiente" in html


def test_sin_saldo_el_analisis_de_meta_da_402_y_no_guarda_nada(mixto):
    _sembrar()
    _cobra()
    r = _analizar(mixto, "meta", "m2")
    assert r.status_code == 402 and r.get_json()["saldo_insuficiente"] is True
    assert _jobs() == [] and _filas() == []


def test_el_precio_de_un_anuncio_de_meta_usa_la_duracion_que_ya_se_vio(mixto):
    """G2 (revisión final de Rendimiento E2, guardián de gasto, 2026-10-10): un anuncio de una cuenta de Meta sin tienda
    no tiene fila en `tw_creativo`, así que su precio suponía 30 s de Whisper aunque un análisis anterior ya hubiera
    traído su video de Meta y guardado `foto.creativo.duracion_s`. Con esa duración (95 s) la tarjeta, el total del lote
    y lo que se reserva al cobrar dicen lo mismo; los demás anuncios de Meta siguen con 30 s."""
    import gastos
    _sembrar()
    al = _alcances()
    # Un análisis anterior de m2 trajo su creativo de Meta (95 s) y falló después: la tarjeta vuelve a ofrecerlo.
    aid = twdatos.crear_analisis("acme", None, "facebook-ads", "m2", al["meta"]["desde"], al["meta"]["hasta"], "SEK",
                                 {"fuente": "meta", "ad_account_id": SE, "metodo": 2,
                                  "creativo": {"tipo": "video", "duracion_s": 95.0}})
    twdatos.actualizar_analisis(aid, estado="error", error="Claude no respondió.")
    noventa = gastos.estimar("analisis_anuncio_tw", segundos=95)["usd"]
    treinta = gastos.estimar("analisis_anuncio_tw")["usd"]
    assert noventa > treinta
    g = _armar()
    precios = {a["ad_id"]: a["precio_analisis"]["usd"] for a in g["tarjetas"]}
    assert precios["m2"] == pytest.approx(noventa) and precios["m1"] == pytest.approx(treinta)
    assert "meta:facebook-ads:m2" in g["lote"]["claves"]
    assert g["lote"]["precio"]["usd"] == pytest.approx(sum(precios[k.rsplit(":", 1)[1]] for k in g["lote"]["claves"]),
                                                       abs=1e-4)
    libro = _cobra(100_000)
    assert _analizar(mixto, "meta", "m2").get_json()["ok"]
    with db.conectar() as con:
        [reserva] = [dict(r._mapping) for r in con.execute(sa.select(db.reserva_saldo))]
    assert reserva["costo_usd"] == pytest.approx(noventa)
    assert reserva["milesimas"] == libro.precio_milesimas(noventa, libro.margen_precio("acme"))


# ------------------------------------------------------------------------------- la tarjeta de Meta ---

def _tarjeta_de(html, k):
    ini = html.index(f'id="tw-tarjeta-{k}"')
    return html[html.rindex("<article", 0, ini):html.index("</article>", ini)]


def test_la_tarjeta_de_meta_postea_a_la_ruta_nueva_con_su_fuente(mixto):
    _sembrar()
    html = _panel(mixto)
    m2, t1 = _tarjeta_de(html, "meta-facebook-ads-m2"), _tarjeta_de(html, "facebook-ads-t1")
    assert 'action="/cliente/acme/rendimiento/anuncio/meta/facebook-ads/m2/analizar"' in m2 and "data-tw-async" in m2
    assert 'data-tarjeta-url="/cliente/acme/rendimiento/tarjeta/meta/facebook-ads/m2?entrada=&amp;dias=0&amp;canal="' in m2
    assert 'name="entrada" value=""' in m2 and 'name="dias" value="0"' in m2 and 'name="tienda"' not in m2
    assert "Cómo mejorarlo" in m2 and "aprox." in m2 and "según Meta" in m2 and "HappyFlops Sweden" in m2
    assert 'action="/cliente/acme/rendimiento/anuncio/tw/facebook-ads/t1/analizar"' in t1
    assert not re.search(r'/triple-whale/anuncio/[^"]*/analizar', html) and "/triple-whale/galeria" not in html
    assert "/triple-whale/tarjeta/" not in html and "/triple-whale/analizar-lote" not in html
    d = _analizar(mixto, "meta", "m2").get_json()
    assert d["ok"] and 'data-poll-job="acme__tw_anuncio__facebook-ads__m2"' in d["html"]
    assert 'data-poll-al-terminar="evento"' in d["html"] and 'id="tw-tarjeta-meta-facebook-ads-m2"' in d["html"]
    [fila] = _filas()
    assert fila["foto"]["fuente"] == "meta" and fila["foto"]["ad_account_id"] == SE
    assert _jobs() == ["acme__tw_anuncio__facebook-ads__m2"]
    # Un segundo clic (otra pestaña) mientras corre: no cobra otra vez.
    d = _analizar(mixto, "meta", "m2").get_json()
    assert d["ok"] is False and "ya se está analizando" in d["mensaje"] and len(_filas()) == 1


def test_la_tarjeta_sola_se_repinta_con_su_fuente(mixto):
    _sembrar()
    r = mixto["c"].get("/cliente/acme/rendimiento/tarjeta/meta/facebook-ads/m1?entrada=&dias=0&canal=")
    assert r.status_code == 200 and r.data.decode().count('<article class="tw-tarjeta') == 1
    assert 'id="tw-tarjeta-meta-facebook-ads-m1"' in r.data.decode()
    r = mixto["c"].get("/cliente/acme/rendimiento/tarjeta/tw/facebook-ads/t1?entrada=&dias=0&canal=")
    assert r.status_code == 200 and 'id="tw-tarjeta-facebook-ads-t1"' in r.data.decode()


def test_meta_sin_referentes_ni_meta_reporta(mixto):
    _sembrar()
    tid = triple_whale_tiendas.tiendas("acme")[0]["id"]
    for n in range(5):                    # t1 con lo que Meta le informa a Triple Whale y una miniatura de Triple Whale
        f = _hace(n)
        twdatos.reemplazar_anuncios_canal("acme", tid, f, f, [
            {"canal": "facebook-ads", "ad_id": "t1", "fecha": f, "anuncio": "Anuncio t1", "gasto": 30,
             "impresiones": 3000, "clics": 60, "vistas_3s": 900, "thruplays": 300, "valor_canal": 120}])
    twdatos.reemplazar_creativos("acme", tid, [{"canal": "facebook-ads", "ad_id": "t1", "tipo": "imagen",
                                                "imagen_url": "https://files.triplewhale.com/t/t1.jpg"}])
    mdatos.guardar_objetos("acme", SE, [{"nivel": "anuncio", "objeto_id": "m2", "nombre": "Video m2",
                                         "estado": "ACTIVE", "miniatura_url": "https://scontent.xx.fbcdn.net/m2.jpg"}])
    html = _panel(mixto, "?veredicto=")
    m2, t1 = _tarjeta_de(html, "meta-facebook-ads-m2"), _tarjeta_de(html, "facebook-ads-t1")
    assert "Meta reporta" in t1 and "Meta reporta" not in m2
    assert "Guardar en Referentes" not in m2 and "/referente" not in m2
    assert "tw-tarjeta-ganador" in t1 and "tw-tarjeta-ganador" in m2              # los dos ganadores, con imagen
    assert "/triple-whale/anuncio/facebook-ads/t1/referente" in t1 and "Guardar en Referentes" in t1
    assert 'name="tienda"' in t1.split("/referente")[1].split("</form>")[0]     # con el alcance de Triple Whale


def test_el_medio_de_la_tarjeta_de_meta(mixto, monkeypatch):
    """Regla 4: la miniatura de Meta solo si su host es de Meta (también al pintarla: PND-282); con un análisis listo,
    la imagen que el análisis copió a R2."""
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://media.creatv.test")
    _sembrar()
    mdatos.guardar_objetos("acme", SE, [
        {"nivel": "anuncio", "objeto_id": "m2", "nombre": "Video m2", "estado": "ACTIVE",
         "miniatura_url": "https://scontent.xx.fbcdn.net/m2.jpg"},
        {"nivel": "anuncio", "objeto_id": "m1", "nombre": "Video m1", "estado": "ACTIVE",
         "miniatura_url": "https://scontent.xx.fbcdn.net/m1.jpg"}])
    with db.conectar() as con:          # una fila vieja (o escrita por otro camino) con un host que no es de Meta
        con.execute(db.meta_objeto.update().where(db.meta_objeto.c.objeto_id == "m1")
                    .values(miniatura_url="https://evil.test/m1.jpg"))
    html = _panel(mixto)
    m2, m1 = _tarjeta_de(html, "meta-facebook-ads-m2"), _tarjeta_de(html, "meta-facebook-ads-m1")
    assert 'src="https://scontent.xx.fbcdn.net/m2.jpg"' in m2 and 'loading="lazy"' in m2 and "no-referrer" in m2
    assert 'class="tw-medio-miniatura"' in m2                 # la de Meta es de 64 px: a su tamaño, sin agrandarla
    assert "evil.test" not in m1 and "<img" not in m1
    al = _alcances()
    a = next(x for x in al["meta"]["ev"]["anuncios"] if x["ad_id"] == "m1")
    imagen = "https://media.creatv.test/clientes/acme/triple_whale/m1.jpg"
    aid = twdatos.crear_analisis("acme", None, "facebook-ads", "m1", al["meta"]["desde"], al["meta"]["hasta"], "SEK",
                                 {"metodo": 2, "veredicto": a["veredicto"], "m": {"gasto": a["m"]["gasto"]},
                                  "fuente": "meta", "creativo": {"imagen_url": imagen}})
    twdatos.actualizar_analisis(aid, estado="lista", resultado={"frase": "Gana por el arranque."})
    m1 = _tarjeta_de(_panel(mixto), "meta-facebook-ads-m1")
    assert f'src="{imagen}"' in m1 and "Gana por el arranque." in m1 and "tw-medio-miniatura" not in m1


# ------------------------------------------------------------------------------ consultas por página ---

def _por_fuente(n, tid=None):
    """`n` anuncios en cada fuente, con gastos entrelazados por USD: la primera página siempre lleva de las dos."""
    tw = [(f"t{i:02d}", 20 + 2 * i) for i in range(n)]
    meta = [(f"m{i:02d}", 210 + 20 * i) for i in range(n)]
    if tid is None:
        return _sembrar(tw=tw, meta=meta, poco=False)
    _anuncios(tid, tw, meta)
    return tid


def _contar(fn):
    from tests.test_escala import _Consultas
    with _Consultas() as c:
        fn()
    return c.n


def _frio(app, url):  # noqa: F811
    d = app["dashboard"]
    d._TABLERO_CACHE.clear()
    d.invalidar_alertas("acme")
    r = app["c"].get(url)
    assert r.status_code == 200
    return r.data.decode()


@pytest.mark.parametrize("url", ["/cliente/acme/rendimiento/galeria?entera=1",
                                 "/cliente/acme/rendimiento/galeria?pagina=2",
                                 "/cliente/acme/rendimiento/panel"])
def test_las_consultas_no_crecen_con_las_tarjetas(mixto, url):
    """12 y 24 anuncios por fuente: el mismo número de consultas (una por bloque, nunca una por tarjeta)."""
    tid = _por_fuente(12)
    _frio(mixto, url)               # la primera petición del proceso llena cachés del proceso: no es de la galería
    doce = _contar(lambda: _frio(mixto, url))
    html = _frio(mixto, "/cliente/acme/rendimiento/galeria?entera=1")
    assert {"tw", "meta"} <= set(re.findall(r'data-fuente="(\w+)"', html))
    _por_fuente(24, tid)
    veinticuatro = _contar(lambda: _frio(mixto, url))
    assert doce == veinticuatro, (doce, veinticuatro)


# -------------------------------------------------------------------------------- ajenos y seguridad ---

def test_foraneas_e_invalidas_son_404(mixto):
    _sembrar()
    twdatos.crear_analisis("otro", None, "facebook-ads", "zz", "2026-09-01", "2026-09-30", "USD", {})
    c = mixto["c"]
    for url in ("/cliente/acme/rendimiento/tarjeta/meta/facebook-ads/no-existe",
                "/cliente/acme/rendimiento/tarjeta/meta/facebook-ads/t1",        # de Triple Whale, no de Meta
                "/cliente/acme/rendimiento/tarjeta/tw/facebook-ads/m1",
                "/cliente/acme/rendimiento/tarjeta/x/facebook-ads/m1",
                "/cliente/acme/rendimiento/tarjeta/meta/facebook-ads/a%2Fb",
                "/cliente/acme/rendimiento/tarjeta/meta/facebook-ads/zz"):
        assert c.get(url).status_code == 404, url
    for fuente, ad in (("meta", "no-existe"), ("meta", "t1"), ("tw", "m1"), ("x", "m1"), ("meta", "zz")):
        assert _analizar(mixto, fuente, ad).status_code == 404, (fuente, ad)
    assert c.post("/cliente/acme/rendimiento/anuncio/meta/facebook-ads/a%2Fb/analizar", headers=POST).status_code == 404
    assert _jobs() == [] and len(_filas()) == 1                               # solo la fila ajena que sembré


def test_otro_proyecto_no_ve_ni_cobra(mixto):
    from tests.test_rutas_meta_rendimiento import _como_cliente
    _sembrar()
    c = _como_cliente(mixto, usuario="otro", cliente="otro")
    for url in ("/cliente/acme/rendimiento/galeria?entera=1", "/cliente/acme/rendimiento/tarjeta/meta/facebook-ads/m1"):
        r = c.get(url)
        assert r.status_code in (302, 403, 404) and "m1" not in r.data.decode(), url
    r = c.post("/cliente/acme/rendimiento/anuncio/meta/facebook-ads/m1/analizar", data={"entrada": "", "dias": "0"},
               headers=POST)
    assert r.status_code in (302, 403, 404)
    r = c.post("/cliente/acme/rendimiento/analizar-lote", data={"clave": ["meta:facebook-ads:m1"]}, headers=POST)
    assert r.status_code in (302, 403, 404) and _jobs() == [] and _filas() == []
    assert mixto["c"].get("/cliente/otro/rendimiento/galeria?entera=1").status_code == 404     # sin nada conectado


def test_los_post_de_otro_sitio_son_403(mixto):
    _sembrar()
    assert _analizar(mixto, "meta", "m2", **{"Sec-Fetch-Site": "cross-site"}).status_code == 403
    r = mixto["c"].post("/cliente/acme/rendimiento/analizar-lote", data={"clave": ["meta:facebook-ads:m2"]},
                        headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and _jobs() == []


def test_sin_correo_verificado_un_cliente_no_cobra(mixto):
    import usuarios
    from tests.test_rutas_meta_rendimiento import _como_cliente
    _sembrar()
    usuarios.actualizar("user_acme", correo_verificado=False)
    c = _como_cliente(mixto)
    r = c.post("/cliente/acme/rendimiento/anuncio/meta/facebook-ads/m2/analizar",
               data={"entrada": "", "dias": "0", "canal": ""}, headers=dict(POST, Accept="application/json"))
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] is False and d["html"] == "" and "Confirma tu correo" in d["mensaje"]
    r = c.post("/cliente/acme/rendimiento/analizar-lote", data={"clave": ["meta:facebook-ads:m2"]}, headers=POST)
    assert r.status_code == 302 and r.headers["Location"].endswith("#settings")
    assert _jobs() == [] and _filas() == []
    assert c.get("/cliente/acme/rendimiento/galeria?entera=1").status_code == 200      # leer no es escribir


def test_una_entrada_que_ya_no_existe_no_cobra(mixto):
    """Una pestaña vieja (un país que se quitó): no se ensancha a «Todas» para cobrar con otro alcance."""
    _sembrar()
    d = _analizar(mixto, "meta", "m2", entrada="DK").get_json()
    assert d["ok"] is False and d["html"] == "" and "Esa vista ya no existe" in d["mensaje"]
    r = _lote(mixto, ["meta:facebook-ads:m2"], entrada="DK")
    assert "Esa vista ya no existe" in r.data.decode() and _jobs() == [] and _filas() == []
    assert mixto["c"].get("/cliente/acme/rendimiento/galeria?entera=1&entrada=DK").status_code == 404


def test_sin_meta_conectado_la_tarjeta_de_meta_no_cobra(app):  # noqa: F811
    """Sin token (Meta desconectado después de pintar): ni alcance de Meta ni cobro, y el fetch recibe JSON."""
    with app["dashboard"].app.test_request_context():
        _sembrar()
    d = _analizar(app, "meta", "m2").get_json()
    assert d["ok"] is False and d["html"] == "" and _jobs() == []


# ------------------------------------------------------------------------------- traspasos de E2 ---

def test_la_tarea_declara_la_etapa_de_meta():
    from tareas import triple_whale as tareas_tw
    etapas = [nombre for nombre, _ in tareas_tw.ETAPAS_ANALIZAR]
    assert etapas[0] == "Trayendo el anuncio de Meta" and "Analizando con Claude" in etapas
    with open(tareas_tw.__file__, encoding="utf-8") as f:
        fuente = f.read()
    for nombre in etapas:                            # cada etapa declarada es una que la tarea reporta
        assert f'etapa=idiomas.N_("{nombre}")' in fuente, nombre


def test_el_panel_ya_no_tiene_el_bloque_de_tarjetas_de_meta_de_e1(mixto):
    _sembrar()
    html = _panel(mixto)
    assert html.count('id="tw-galeria"') == 1 and 'id="rend-anuncios-meta"' not in html
    assert "rend-tarjeta" not in html and "data-rend-mas" not in html
    assert "De tus cuentas de Meta sin tienda en Triple Whale" not in html
    assert mixto["c"].get("/cliente/acme/rendimiento/anuncios-meta").status_code == 404


# ------------------------------------------- revisión de la tarea 4: un análisis es de SU fuente (A1) ---

def _sembrar_cubierta():
    """Dos tiendas (NO y DK, así «Todas» mira «todas las tiendas», `tienda_id` None) y la cuenta World Wide de Meta,
    cuyos anuncios llegan en la copia de la tienda de Noruega: en «Todas» w1 y w2 son tarjetas de Triple Whale (R5) y,
    vista sola, la cuenta es de fuente Meta (R3): los MISMOS anuncios, con el mismo canal `facebook-ads`, son tarjetas
    de Meta. Las filas y los job_id de un análisis van por (canal, ad_id), sin fuente."""
    t_no = triple_whale_tiendas.agregar("acme", "tw_llave_123", "acme-no.myshopify.com", "NO", moneda="USD")  # llave-de-prueba
    t_dk = triple_whale_tiendas.agregar("acme", "tw_llave_456", "acme-dk.myshopify.com", "DK", moneda="USD")  # llave-de-prueba
    for t in (t_no, t_dk):
        triple_whale_tiendas.actualizar_tienda("acme", t, ultima_sincronizacion=db.ahora())
    mcuentas.elegir("acme", [{"id": "act_ww", "name": "World Wide", "currency": "USD", "pais": None}])
    canal, pixel = [], []
    for n in range(40):
        f = _hace(n)
        mdatos.reemplazar_cuenta_dias("acme", "act_ww", f, f, [_dia(f, 700, 1400, compras=3)])
        mdatos.reemplazar_anuncio_dias("acme", "act_ww", f, f, [_ad(f, "w1", 100, 50, compras=1),
                                                                _ad(f, "w2", 100, 400, compras=4)])
        for ad in ("w1", "w2"):
            canal.append({"canal": "facebook-ads", "ad_id": ad, "fecha": f, "anuncio": ad, "gasto": 100,
                          "impresiones": 5000, "clics": 100, "vistas_3s": 1500, "thruplays": 500, "cuenta_id": "act_ww"})
            pixel.append({"canal": "facebook-ads", "ad_id": ad, "fecha": f, "pedidos": 3 if ad == "w1" else 1,
                          "ingresos": 400 if ad == "w1" else 50})
    twdatos.reemplazar_anuncios_canal("acme", t_no, _hace(39), _hace(0), canal)
    twdatos.reemplazar_anuncios_pixel("acme", t_no, _hace(39), _hace(0), pixel)
    twdatos.reemplazar_tienda("acme", t_no, _hace(39), _hace(0),
                              [{"fecha": _hace(n), "gasto": 200, "ingresos": 450, "pedidos": 4} for n in range(40)])


def _w1_listo(app, fuente, entrada):  # noqa: F811
    """Pide «Cómo mejorarlo» de w1 desde la tarjeta de `fuente` (30 días) y lo deja listo, como cuando el worker
    termina."""
    r = app["c"].post(f"/cliente/acme/rendimiento/anuncio/{fuente}/facebook-ads/w1/analizar",
                      data={"entrada": entrada, "dias": "30", "canal": ""}, headers=dict(POST, Accept="application/json"))
    assert r.get_json()["ok"], r.get_json()
    with db.conectar() as con:
        con.execute(db.tarea.update().values(estado="hecha"))
    [fila] = twdatos.ultimos_analisis("acme", [("facebook-ads", "w1")]).values()
    twdatos.actualizar_analisis(fila["id"], estado="lista", resultado={"frase": f"Frase de {fuente}"})
    return fila


def _desde_la_otra_fuente(app, fuente_vista, entrada_vista, fuente_pagada):  # noqa: F811
    al = rend_panel.alcances("acme", 30, entrada_vista, None)
    alc = al[fuente_vista]
    assert alc and alc.get("fuente", "triple_whale") != ("meta" if fuente_pagada == "meta" else "triple_whale")
    g = galeria.armar("acme", al["tw"], al["meta"], "", 1)
    w1 = next(a for a in g["tarjetas"] if a["ad_id"] == "w1")
    assert w1["fuente"] == fuente_vista
    # El análisis de la otra fuente no es «el mismo alcance»: ni viejo ni ofrecido como botón principal ni en el lote;
    # se ve como de otro alcance (nota neutra y solo «Analizar con estos datos»).
    filas = twdatos.analisis_de_anuncios("acme", [("facebook-ads", "w1")])[("facebook-ads", "w1")]
    from triple_whale import panel as tw_panel
    e = tw_panel.elegir_analisis(w1, filas, alc)
    assert e["mismo"] is None and e["otro_alcance"] and not e["viejo"] and not e["ofrecer"]
    assert w1["analisis_otro_alcance"] and not w1["analisis_viejo"] and not w1["ofrecer_analisis"]
    clave = f"{fuente_vista}:facebook-ads:w1"
    assert clave not in g["lote"]["claves"] and clave not in g["lote"]["elegibles"]
    html = app["c"].get(f"/cliente/acme/rendimiento/tarjeta/{fuente_vista}/facebook-ads/w1"
                        f"?entrada={entrada_vista}&dias=30&canal=").data.decode()
    assert "Analizado con los datos del" in html and "Analizar con estos datos" in html
    assert "Analizar otra vez" not in html and "desde entonces cambió" not in html and "Cómo mejorarlo" not in html
    # El lote de esa vista (y uno forjado con w1) no lo cobra; un segundo envío no cobra nada.
    antes = len(_filas())
    formulario = list(g["lote"]["claves"]) + [clave]
    _lote(app, formulario, entrada=entrada_vista, dias="30")
    nuevas = [f for f in _filas()[antes:]]
    assert all(f["ad_id"] != "w1" for f in nuevas)
    total = len(_filas())
    r = _lote(app, formulario, entrada=entrada_vista, dias="30")
    assert len(_filas()) == total and "No quedó ningún anuncio por analizar" in r.data.decode()


def test_un_analisis_de_triple_whale_no_es_el_de_la_tarjeta_de_meta(mixto):
    _sembrar_cubierta()
    fila = _w1_listo(mixto, "tw", "")
    assert fila["foto"]["fuente"] == "triple_whale"
    _desde_la_otra_fuente(mixto, "meta", "cuenta:act_ww", "tw")


def test_un_analisis_de_meta_no_es_el_de_la_tarjeta_de_triple_whale(mixto):
    _sembrar_cubierta()
    fila = _w1_listo(mixto, "meta", "cuenta:act_ww")
    assert fila["foto"]["fuente"] == "meta"
    _desde_la_otra_fuente(mixto, "tw", "", "meta")


def test_mismo_alcance_compara_la_fuente():
    from triple_whale import panel as tw_panel
    base = {"tienda_id": None, "desde": "2026-09-11", "hasta": "2026-10-10"}
    tw, meta = dict(base), dict(base, fuente="meta")
    assert tw_panel.mismo_alcance(dict(base, foto={}), tw)                      # una fila vieja es de Triple Whale
    assert tw_panel.mismo_alcance(dict(base, foto={"fuente": "triple_whale"}), tw)
    assert not tw_panel.mismo_alcance(dict(base, foto={"fuente": "meta"}), tw)
    assert tw_panel.mismo_alcance(dict(base, foto={"fuente": "meta"}), meta)
    assert not tw_panel.mismo_alcance(dict(base, foto={}), meta)
    assert not tw_panel.mismo_alcance(dict(base, foto={"fuente": "triple_whale"}), meta)
