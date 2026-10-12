"""Cálculo de «Resultados de tu tienda» (spec 2026-10-08-tw-resultados §3): días completos, hoy aparte, días raros,
mejor día, lectura con reglas, creativos por mes y el detalle de un día."""
from datetime import date, timedelta

import pytest

import idiomas
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from triple_whale import resultados as r


@pytest.fixture()
def es():
    with idiomas.en_idioma("es"):
        yield


def _dias(valores, desde="2026-09-01"):
    d0 = date.fromisoformat(desde)
    return [{"f": (d0 + timedelta(days=i)).isoformat(), "ing": ing, "gas": gas, "ped": ped, "nc": 0}
            for i, (ing, gas, ped) in enumerate(valores)]


def _armar(serie, dias_periodo=0, inicio=0, hoy=date(2026, 9, 30), nuevos=None, canales=None, cohortes=None,
           inicio_copia="2026-09-01", meta_roas=None, canal=None, fuente="tienda", ultima_copia=None,
           inicio_datos=None, fin_datos=None, con_detalle=True, inicio_detalle=None):
    return r.armar(dias_periodo=dias_periodo, serie_larga=serie, inicio=inicio, hoy=hoy, fuente=fuente,
                   moneda="USD", nuevos=nuevos or {}, canales=canales or {}, cohortes=cohortes,
                   inicio_copia=inicio_copia, meta_roas=meta_roas, canal=canal, url_dia="/x/dia?tienda=",
                   ultima_copia=ultima_copia, inicio_datos=inicio_datos, fin_datos=fin_datos,
                   con_detalle=con_detalle, inicio_detalle=inicio_detalle)


def test_por_dia_rellena_con_ceros():
    filas = [{"fecha": "2026-09-02", "ingresos": 10, "gasto": 4, "pedidos": 1, "visitantes": 80,
              "visitantes_nuevos": 30}]
    assert r.por_dia("2026-09-01", "2026-09-03", filas) == [
        {"f": "2026-09-01", "ing": 0.0, "gas": 0.0, "ped": 0.0, "nc": 0.0, "vis": 0.0, "vnu": 0.0},
        {"f": "2026-09-02", "ing": 10.0, "gas": 4.0, "ped": 1.0, "nc": 0.0, "vis": 80.0, "vnu": 30.0},
        {"f": "2026-09-03", "ing": 0.0, "gas": 0.0, "ped": 0.0, "nc": 0.0, "vis": 0.0, "vnu": 0.0}]


def test_razones_de_periodo_salen_de_las_sumas_y_divisor_cero_es_none():
    dias = _dias([(100, 50, 2), (300, 50, 2)])
    tot = r.totales(dias)
    assert r.valor_periodo("mer", tot) == 4.0 and r.valor_periodo("ticket", tot) == 100.0
    assert r.valor("cpp", {"ing": 0, "gas": 5, "ped": 0}) is None


def test_variacion_tono_y_bueno():
    a, p = _dias([(110, 50, 2)]), _dias([(100, 50, 2)])
    assert r.variacion("ventas", a, p) == pytest.approx(0.10)
    assert r.variacion("ventas", a, _dias([(0, 0, 0)])) is None
    assert r.variacion("ventas", a, []) is None
    assert (r.bueno("ventas"), r.bueno("gasto"), r.bueno("cpp")) == (1, 0, -1)
    assert (r.tono("ventas", -0.2), r.tono("cpp", -0.2), r.tono("gasto", 0.5), r.tono("ventas", 0.001)) == (
        "malo", "bueno", "neutro", "neutro")


def test_raros_mediana_de_4_semanas_umbral_maximo_3_y_hoy_fuera():
    # 4 semanas de 100 y luego: un día +50 %, uno −40 %, uno +30 %, uno +26 %, uno +10 % y hoy +300 %.
    base = [(100, 50, 1)] * 28
    periodo = [(150, 50, 1), (60, 50, 1), (130, 50, 1), (126, 50, 1), (110, 50, 1), (400, 50, 1)]
    raros = r.raros("ventas", _dias(base + periodo), inicio=28)
    assert raros == {0: pytest.approx(0.5), 1: pytest.approx(-0.4), 2: pytest.approx(0.3)}   # el +26 % no entra


def test_raros_pide_3_semanas_con_dato():
    serie = _dias([(100, 50, 1)] * 14 + [(300, 50, 1), (1, 1, 1)])
    assert r.raros("ventas", serie, inicio=14) == {}


def test_mejor_dia_y_costo_por_pedido_al_reves():
    dias = _dias([(100, 50, 1), (300, 60, 3), (200, 10, 1)])
    assert r.mejor_dia("ventas", dias) == 1 and r.mejor_dia("cpp", dias) == 2
    assert r.mejor_dia("ventas", _dias([(0, 0, 0)])) is None


def test_lectura_como_vas_solo_con_comparacion(es):
    a, p = _dias([(110, 50, 2)] * 6), _dias([(100, 50, 2)] * 6)
    frases = r.lectura(a, p, True, {}, {}, "USD", "tienda")
    assert "10 % más" in frases[0]["texto"] and "1 USD en anuncios" in frases[0]["texto"]
    assert frases[0]["tipo"] == "ok"
    assert all("anteriores" not in f["texto"] for f in r.lectura(a, p, False, {}, {}, "USD", "tienda"))


def test_lectura_mejor_dia_con_accion(es):
    a = _dias([(100, 50, 2), (900, 50, 9)])
    mejor = [f for f in r.lectura(a, [], False, {}, {}, "USD", "tienda") if f["icono"] == "★"][0]
    assert "900 USD" in mejor["texto"] and "9 pedidos" in mejor["texto"] and "miércoles 2 de septiembre" in mejor["texto"]
    assert mejor["acciones"] == [{"tipo": "dia", "fecha": a[1]["f"]}]


def test_lectura_aviso_de_anuncios_nuevos(es):
    a = _dias([(100, 100, 1)] * 10)
    nuevos = {d["f"]: 50.0 for d in a[:8]} | {d["f"]: 5.0 for d in a[8:]}
    avisos = [f for f in r.lectura(a, [], False, nuevos, {}, "USD", "tienda") if f["tipo"] == "aviso"]
    assert avisos and "5 % del gasto" in avisos[0]["texto"]
    assert [x["tipo"] for x in avisos[0]["acciones"]] == ["crear", "evaluar"]
    sin_caida = {d["f"]: 50.0 for d in a}
    assert not [f for f in r.lectura(a, [], False, sin_caida, {}, "USD", "tienda") if f["tipo"] == "aviso"]
    pocos_dias = {d["f"]: 50.0 for d in a[:4]} | {d["f"]: 5.0 for d in a[4:6]}      # solo 6 días conocidos
    assert not [f for f in r.lectura(a[:6], [], False, pocos_dias, {}, "USD", "tienda") if f["tipo"] == "aviso"]


def test_lectura_por_canal_sin_canales_chicos(es):
    a = _dias([(100, 100, 1)])
    canales = {a[0]["f"]: {"facebook-ads": {"gasto": 89, "ingresos": 178},
                           "google-ads": {"gasto": 10.5, "ingresos": 357},
                           "tiktok-ads": {"gasto": 0.5, "ingresos": 1}}}
    frase = [f for f in r.lectura(a, [], False, {}, canales, "USD", "tienda") if f["icono"] == "◎"][0]["texto"]
    assert frase.startswith("Por canal, según el Pixel: Meta, 89 % del gasto y 2,00× de retorno; Google Ads")
    assert "TikTok" not in frase
    assert not [f for f in r.lectura(a, [], False, {}, canales, "USD", "anuncios") if f["icono"] == "◎"]


def test_creativos_por_mes_con_o_antes(es):
    c = {"meses": [{"mes": "2026-07", "anuncios": 3, "gasto": 10, "ingresos": 60},
                   {"mes": "2026-08", "anuncios": 2, "gasto": 30, "ingresos": 40}],
         "nuevos": {"gasto": 30, "ingresos": 40}, "establecidos": {"gasto": 10, "ingresos": 60}, "probados": 2}
    out = r.creativos(c, "2026-07-10")
    assert out["meses"][0]["nombre"] == "julio o antes" and out["meses"][1]["nombre"] == "agosto"
    assert out["meses"][0]["pct_ingresos"] == pytest.approx(0.6) and out["meses"][1]["clase"] == "mes-5"
    assert out["roas_nuevos"] == pytest.approx(40 / 30) and out["probados"] == 2
    assert r.creativos(dict(c, meses=c["meses"][:1]), "2026-07-10")["meses"] == []   # un solo mes: sin barras
    assert r.creativos(c, "2026-07-01")["meses"][0]["nombre"] == "julio"             # la copia arrancó el día 1
    assert r.creativos(None, "2026-07-01") is None


def test_creativos_funde_los_meses_mas_viejos(es):
    meses = [{"mes": f"2026-0{m}", "anuncios": 1, "gasto": 10, "ingresos": 10} for m in range(2, 9)]
    out = r.creativos({"meses": meses, "probados": 0}, "2026-02-01")
    assert len(out["meses"]) == r.MAX_MESES and out["meses"][0]["nombre"] == "abril o antes"
    assert out["meses"][0]["anuncios"] == 3


def test_armar_desde_el_inicio_sin_comparacion_y_hoy_aparte(es):
    serie = _dias([(100, 50, 2)] * 30)
    serie[-1] = dict(serie[-1], ing=10, gas=5, ped=1)
    out = _armar(serie, meta_roas=2.0, ultima_copia="2026-09-30T06:14:00")
    assert out["datos"]["comparar"] is False and out["datos"]["previos"] == []
    assert all(t["variacion"] is None for t in out["tarjetas"])
    assert out["tarjetas"][0]["valor"] == pytest.approx(100 * 29 + 10)      # el total incluye hoy
    assert out["datos"]["dia_inicial"] == "2026-09-29" and "06:14" in out["hoy_texto"]
    assert out["datos"]["dias"][-1]["f"] == "2026-09-30" and out["titulo"] == "Resultados de tu tienda"
    assert "todo lo copiado de Triple Whale" in out["subtitulo"]
    assert [t["clave"] for t in out["tarjetas"]] == list(r.METRICAS)      # sin clientes nuevos: nc en 0
    assert out["tabla"][0]["hoy"] is True and out["tabla"][0]["f"] == "2026-09-30"


def test_armar_con_periodo_compara_dias_completos(es):
    serie = _dias([(100, 50, 2)] * 23 + [(200, 50, 2)] * 6 + [(1, 1, 1)])   # 30 días: 23 + 6 completos + hoy
    out = _armar(serie, dias_periodo=7, inicio=23)
    ventas = out["tarjetas"][0]
    assert ventas["variacion"] == pytest.approx(1.0) and ventas["tono"] == "bueno"   # hoy fuera de la comparación
    assert ventas["variacion_texto"] == "100 %"
    assert len(out["datos"]["previos"]) == 6 and out["datos"]["comparar"] is True
    assert "6 días completos" in out["subtitulo"]


def test_armar_sin_datos_previos_no_compara(es):
    serie = _dias([(0, 0, 0)] * 6 + [(200, 50, 2)] * 7)
    out = _armar(serie, dias_periodo=7, inicio=6)
    assert out["datos"]["comparar"] is False and out["tarjetas"][0]["variacion"] is None


def test_periodo_anterior_antes_de_la_copia_no_se_compara(es):
    """90 días con 91 copiados: el periodo anterior caería casi entero antes de la copia (ceros que no son ventas
    en cero) y daría una subida inventada."""
    serie = _dias([(0, 0, 0)] * 5 + [(100, 50, 2)] * 12)
    out = _armar(serie, dias_periodo=7, inicio=10, inicio_datos=serie[5]["f"])
    assert out["datos"]["comparar"] is False and out["tarjetas"][0]["variacion"] is None
    assert _armar(serie, dias_periodo=7, inicio=10, inicio_datos=serie[4]["f"])["datos"]["comparar"] is True


def test_raros_no_cuentan_semanas_de_antes_de_la_copia():
    # 2 semanas antes de la copia (ceros) + 2 dentro a 100 y un día normal de 100: sin el mínimo, la mediana de
    # [100, 100, 0, 0] es 50 y el día «sube 100 %»; con el mínimo solo hay 2 semanas previas y no se juzga.
    serie = _dias([(0, 0, 0)] * 14 + [(100, 50, 1)] * 14 + [(100, 50, 1), (1, 1, 1)])
    assert r.raros("ventas", serie, inicio=28, minimo=0) == {0: pytest.approx(1.0)}
    assert r.raros("ventas", serie, inicio=28, minimo=14) == {}


def test_antiguedad_desconocida_antes_de_14_dias_de_copia(es):
    serie = _dias([(100, 50, 2)] * 30)
    out = _armar(serie, nuevos={d["f"]: 10.0 for d in serie})
    dias = out["datos"]["dias"]
    assert dias[13]["nue"] is None and dias[14]["nue"] == 10.0             # 1–14 sep desconocido; desde el 15, sí
    assert out["datos"]["conocido_desde"] == "2026-09-15"


def test_armar_por_canal_y_clientes_nuevos(es):
    serie = [dict(d, nc=1) for d in _dias([(100, 50, 2)] * 10)]
    canales = {serie[0]["f"]: {"facebook-ads": {"gasto": 40, "ingresos": 1}, "organic": {"gasto": 0, "ingresos": 9},
                               "bing": {"gasto": 10, "ingresos": 1}}}
    out = _armar(serie, canales=canales)
    assert out["datos"]["dias"][0]["can"] == {"meta": 40, "otros": 10}
    assert [c["clase"] for c in out["datos"]["canales"]] == ["meta", "otros"]
    assert out["tarjetas"][-1]["clave"] == "clientes_nuevos" and out["tarjetas"][-1]["texto"] == "50 %"
    tt = _armar(serie, fuente="anuncios", canal="tiktok-ads")
    assert tt["titulo"] == "Resultados de TikTok" and tt["tarjetas"][0]["etiqueta"] == "Ventas atribuidas"
    assert "can" not in tt["datos"]["dias"][0]


def test_detalle_dia(es):
    anuncios = [{"canal": "facebook-ads", "ad_id": "a1", "anuncio": "Otoño 1", "gasto": 10.0, "ingresos": 50.0,
                 "pedidos": 1.0, "nuevo": True},
                {"canal": "google-ads", "ad_id": "g1", "anuncio": None, "gasto": 4.0, "ingresos": 0.0,
                 "pedidos": 0.0, "nuevo": False}]
    d = r.detalle_dia("2026-09-17", {"ing": 200, "gas": 50, "ped": 4}, {"ing": 100, "gas": 50, "ped": 2},
                      {"facebook-ads": {"gasto": 10, "ingresos": 50}, "google-ads": {"gasto": 4, "ingresos": 0}},
                      anuncios, 3, {"a1": {"experimento_id": 7, "experimento": "Prueba"}}, "USD", "tienda",
                      "2026-09-16", None)
    assert d["titulo"] == "Qué pasó el jueves 17 de septiembre"
    assert "jueves 10 de septiembre" in d["comparado"]
    assert d["stats"][0]["variacion_texto"] == "▲ 100 %" and d["stats"][0]["tono"] == "bueno"
    assert [c["nombre"] for c in d["canales"]] == ["Meta", "Google Ads"]
    assert d["anuncios"][0]["creatv"]["experimento_id"] == 7 and d["anuncios"][1]["nombre"] == "g1"
    assert d["anuncios"][1]["creatv"] is None and d["arrancaron"] == 3
    sin_antes = r.detalle_dia("2026-09-17", {"ing": 1, "gas": 1, "ped": 1}, None, {}, [], 0, {}, "USD", "tienda",
                              None, None)
    assert sin_antes["comparado"] is None and sin_antes["stats"][0]["variacion_texto"] == ""


def test_dia_semana_en_los_dos_idiomas():
    assert idiomas.dia_semana(date(2026, 9, 17), "es") == "jueves 17 de septiembre"
    assert idiomas.dia_semana(date(2026, 9, 17), "en") == "Thursday, September 17"


# ---- revisión 2026-10-08: lo que el revisor rompió sin que una prueba avisara ----

def test_fuente_anuncios_dice_que_es_lo_que_atribuye_el_pixel(es):
    serie = _dias([(100, 50, 2)] * 23 + [(200, 50, 2)] * 6 + [(1, 1, 1)])
    out = _armar(serie, dias_periodo=7, inicio=23, fuente="anuncios", canal="tiktok-ads")
    textos = " ".join(f["texto"] for f in out["lectura"])
    assert "Según el Pixel, estos anuncios vendieron" in textos and "en ventas atribuidas según el Pixel" in textos
    assert "Vendiste" not in textos and "Tu mejor día" not in textos
    assert "según el Pixel" in out["hoy_texto"]
    tarjetas = {t["clave"]: t for t in out["tarjetas"]}
    assert "Pixel" in tarjetas["mer"]["ayuda"] and "tienda" not in tarjetas["mer"]["ayuda"]
    assert tarjetas["cpp"]["etiqueta"] == "Costo por pedido atribuido"
    tienda = {t["clave"]: t for t in _armar(serie, dias_periodo=7, inicio=23)["tarjetas"]}
    assert tienda["mer"]["ayuda"] == "Ventas de la tienda entre todo el gasto en publicidad"


def test_copia_atrasada_no_inventa_una_caida(es):
    # 27 días copiados a 100, dos días sin copiar y hoy: los días sin copia no son ventas en cero.
    serie = _dias([(100, 50, 2)] * 27 + [(0, 0, 0)] * 3)
    out = _armar(serie, dias_periodo=7, inicio=23, inicio_datos=serie[0]["f"], fin_datos=serie[26]["f"])
    ventas = out["tarjetas"][0]
    assert ventas["variacion"] == pytest.approx(0.0) and ventas["valor"] == pytest.approx(400)
    assert len(out["datos"]["previos"]) == 4                                     # 4 días completos contra 4
    dias = out["datos"]["dias"]
    assert dias[4]["sin_copia"] is True and dias[4]["ing"] is None and dias[5]["ing"] is None
    assert out["datos"]["raros"]["ventas"] == {}                                 # los días sin copia no son «raros»
    assert "trae datos hasta el" in out["hoy_texto"] and out["tabla"][1]["ventas"] == "sin copia"
    assert all("menos" not in f["texto"] for f in out["lectura"])


def test_armar_juzga_los_dias_raros_con_el_inicio_de_la_copia(es):
    serie = _dias([(0, 0, 0)] * 14 + [(100, 50, 1)] * 14 + [(100, 50, 1), (1, 1, 1)])
    out = _armar(serie, dias_periodo=0, inicio=28, inicio_datos=serie[14]["f"])
    assert out["datos"]["raros"]["ventas"] == {}


def test_desde_el_inicio_nunca_compara_aunque_haya_dias_antes(es):
    serie = _dias([(100, 50, 2)] * 20 + [(1, 1, 1)])
    out = _armar(serie, dias_periodo=0, inicio=10)
    assert out["datos"]["comparar"] is False and out["datos"]["previos"] == []


def test_borde_del_umbral_de_dias_raros():
    serie = _dias([(100, 50, 1)] * 28 + [(125, 50, 1), (124, 50, 1), (1, 1, 1)])
    assert r.raros("ventas", serie, inicio=28) == {0: pytest.approx(0.25)}     # 25 % entra; 24 % no


def test_borde_de_la_caida_de_anuncios_nuevos(es):
    a = _dias([(100, 100, 1)] * 10)

    def aviso(valor_periodo):
        nuevos = {d["f"]: valor_periodo for d in a[:8]} | {d["f"]: 0.0 for d in a[8:]}
        return [f for f in r.lectura(a, [], False, nuevos, {}, "USD", "tienda") if f["tipo"] == "aviso"]
    assert aviso(18.75)                                                          # 15 puntos justos: avisa
    assert not aviso(18.7)


def test_el_aviso_pide_7_dias_conocidos(es):
    a = _dias([(100, 100, 1)] * 7)
    nuevos = {d["f"]: 50.0 for d in a[:5]} | {d["f"]: 0.0 for d in a[5:]}
    assert [f for f in r.lectura(a, [], False, nuevos, {}, "USD", "tienda") if f["tipo"] == "aviso"]


def test_un_canal_con_el_1_por_ciento_justo_se_nombra(es):
    a = _dias([(100, 100, 1)])
    canales = {a[0]["f"]: {"facebook-ads": {"gasto": 99, "ingresos": 198}, "tiktok-ads": {"gasto": 1, "ingresos": 1}}}
    frase = [f for f in r.lectura(a, [], False, {}, canales, "USD", "tienda") if f["icono"] == "◎"][0]["texto"]
    assert "TikTok" in frase


def test_detalle_dia_sin_antiguedad_conocida(es):
    anuncios = [{"canal": "facebook-ads", "ad_id": "a1", "anuncio": "A", "gasto": 10.0, "ingresos": 5.0,
                 "pedidos": 1.0, "nuevo": True}]
    d = r.detalle_dia("2026-09-03", {"ing": 1, "gas": 1, "ped": 1}, None, {}, anuncios, 6, {}, "USD", "tienda",
                      None, None, antiguedad_conocida=False)
    assert d["anuncios"][0]["nuevo"] is False and d["arrancaron"] is None


# ---- Rendimiento (2/9): fuente Meta y mezcla, y sin detalle del día ----

def test_fuente_meta_dice_segun_meta_y_no_habla_de_triple_whale(es):
    out = _armar(_dias([(100, 50, 2)] * 10), fuente="meta")
    etiquetas = {t["clave"]: t["etiqueta"] for t in out["tarjetas"]}
    assert etiquetas["ventas"] == "Ventas según Meta" and etiquetas["mer"] == "ROAS según Meta"
    textos = " ".join([out["titulo"], out["subtitulo"], out["hoy_texto"]] + [f["texto"] for f in out["lectura"]]
                      + list(out["datos"]["textos"].values()))
    assert "Triple Whale" not in textos and "Pixel" not in textos
    assert "clientes_nuevos" not in etiquetas


def test_fuente_mixta_usa_ventas_y_retorno_sin_apellido(es):
    out = _armar(_dias([(100, 50, 2)] * 10), fuente="mixta")
    etiquetas = {t["clave"]: t["etiqueta"] for t in out["tarjetas"]}
    assert etiquetas["ventas"] == "Ventas" and etiquetas["mer"] == "Retorno"
    assert "Triple Whale" not in out["subtitulo"]


def test_sin_detalle_ninguna_frase_abre_un_dia(es):
    out = _armar(_dias([(100, 50, 2)] * 10), fuente="meta", con_detalle=False)
    assert all(a["tipo"] != "dia" for f in out["lectura"] for a in f["acciones"])
    con = _armar(_dias([(100, 50, 2)] * 10), fuente="tienda")
    assert any(a["tipo"] == "dia" for f in con["lectura"] for a in f["acciones"])


def test_la_plantilla_pinta_el_recuadro_del_detalle_solo_con_url_dia(app):  # noqa: F811
    from flask import render_template

    def pintar(**kw):
        with app["dashboard"].app.test_request_context():
            return render_template("_tw_resultados.html", tw={"resultados": _armar(_dias([(100, 50, 2)] * 10), **kw)})
    con = pintar(fuente="tienda")
    assert 'class="twr-dia"' in con and 'data-twr-dia="2026-' in con                 # recuadro y botón «Ver qué pasó»
    sin = pintar(fuente="meta", con_detalle=False)
    assert 'class="twr-dia"' not in sin and "data-twr-dia" not in sin
    assert "Resultados de tus anuncios en Meta" in sin and "Ventas según Meta" in sin


def test_fuente_meta_llama_compras_al_conteo_y_nunca_pedidos(es):
    # Las tarjetas dicen «Ventas según Meta» (valor) y «Compras según Meta» (conteo): las frases también.
    serie = _dias([(100, 50, 1)] * 5 + [(100, 50, 1), (240, 50, 2), (100, 50, 1), (100, 50, 1), (90, 30, 1)])
    out = _armar(serie, dias_periodo=5, inicio=5, fuente="meta")
    frases = [f["texto"] for f in out["lectura"]]
    mejor = next(t for t in frases if t.startswith("Su mejor día"))
    assert mejor.endswith("en ventas según Meta y 2 compras.") and "compras según Meta y" not in mejor
    assert out["hoy_texto"].startswith("Hoy van 90 USD en ventas según Meta y 1 compra, con 30 USD de gasto.")
    assert any(t.startswith("Según Meta, tus anuncios vendieron") for t in frases)       # la comparación no mezcla
    todo = " ".join(frases + [out["hoy_texto"]] + [t["etiqueta"] + " " + t["ayuda"] for t in out["tarjetas"]])
    assert "pedido" not in todo.lower() and "Compras según Meta" in todo
    # El mismo texto en la fuente mezclada sí habla de pedidos (no cambió).
    mixta = _armar(serie, dias_periodo=5, inicio=5, fuente="mixta")
    assert "2 pedidos" in " ".join(f["texto"] for f in mixta["lectura"]) and "1 pedido" in mixta["hoy_texto"]


# ---- PND-294: los días que el detalle no abre (2026-10-12) ---------------------------------------------------------

def _con_dia_mejor(i_mejor=2, largo=30):
    """`largo` días con el mejor día de ventas en `i_mejor` (los demás venden 100)."""
    return _dias([(900 if i == i_mejor else 100, 50, 2) for i in range(largo)])


def test_los_dias_antes_del_primero_del_detalle_llevan_sin_dia(es):
    serie = _dias([(100, 50, 2)] * 30)                                  # del 1 al 30 de septiembre; hoy = el 30
    out = _armar(serie, fuente="mixta", inicio_detalle="2026-09-10")
    dias = out["datos"]["dias"]
    assert [d["f"] for d in dias if d.get("sin_dia")] == [f"2026-09-{n:02d}" for n in range(1, 10)]
    assert all(d.get("sin_dia") is None for d in dias[9:])               # desde el primero del detalle, ninguno
    assert not dias[-1].get("sin_dia")                                    # hoy tiene su propia regla (el JS)
    # Totales, tarjetas y días dibujados no cambian: solo se marca.
    sin_marcas = _armar(serie, fuente="mixta")
    assert sin_marcas["tarjetas"] == out["tarjetas"] and len(sin_marcas["datos"]["dias"]) == len(dias)
    assert [{k: v for k, v in d.items() if k != "sin_dia"} for d in dias] == sin_marcas["datos"]["dias"]


def test_sin_inicio_detalle_o_sin_detalle_no_se_marca_nada(es):
    serie = _dias([(100, 50, 2)] * 30)
    for out in (_armar(serie, fuente="mixta"),                                              # la sección no marca
                _armar(serie, fuente="mixta", inicio_detalle="2026-09-10", con_detalle=False)):   # nada que abrir
        assert not any(d.get("sin_dia") for d in out["datos"]["dias"])


def test_un_dia_sin_copia_conserva_lo_suyo_y_no_se_marca_sin_dia(es):
    serie = _dias([(100, 50, 2)] * 30)
    out = _armar(serie, fuente="mixta", inicio_detalle="2026-09-10", fin_datos="2026-09-25")
    dias = {d["f"]: d for d in out["datos"]["dias"]}
    assert dias["2026-09-26"]["sin_copia"] is True and "sin_dia" not in dias["2026-09-26"]
    assert dias["2026-09-25"].get("sin_dia") is None and dias["2026-09-09"]["sin_dia"] is True


def test_ninguna_copia_es_ningun_dia_salvo_hoy(es):
    out = _armar(_dias([(100, 50, 2)] * 30), fuente="meta", inicio_detalle=r.NINGUN_DIA)
    dias = out["datos"]["dias"]
    assert all(d["sin_dia"] for d in dias[:-1]) and "sin_dia" not in dias[-1]


def test_ver_que_paso_no_ofrece_un_dia_que_el_detalle_rechaza(es):
    serie = _con_dia_mejor(i_mejor=2)                                     # el mejor día es el 3 de septiembre
    abre = _armar(serie, fuente="mixta", inicio_detalle="2026-09-03")
    cierra = _armar(serie, fuente="mixta", inicio_detalle="2026-09-04")
    acciones = lambda out: [a for f in out["lectura"] for a in f["acciones"] if a["tipo"] == "dia"]   # noqa: E731
    assert acciones(abre) == [{"tipo": "dia", "fecha": "2026-09-03"}] and acciones(cierra) == []
    # La frase sigue diciendo lo mismo: solo se quita el botón que no iba a abrir nada.
    assert [f["texto"] for f in abre["lectura"]] == [f["texto"] for f in cierra["lectura"]]


def test_el_motivo_del_recuadro_depende_de_la_fuente(es):
    serie = _dias([(100, 50, 2)] * 30)
    textos = {fuente: _armar(serie, fuente=fuente)["datos"]["textos"]["sin_dia"]
              for fuente in ("mixta", "meta", "tienda", "anuncios")}
    assert textos["mixta"] == "todavía no estaban todas tus fuentes"
    assert textos["meta"] == textos["tienda"] == textos["anuncios"] == "antes de la primera copia"
