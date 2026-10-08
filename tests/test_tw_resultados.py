"""Cálculo de «Resultados de tu tienda» (spec 2026-10-08-tw-resultados §3): días completos, hoy aparte, días raros,
mejor día, lectura con reglas, creativos por mes y el detalle de un día."""
from datetime import date, timedelta

import pytest

import idiomas
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
           inicio_copia="2026-09-01", meta_roas=None, canal=None, fuente="tienda", ultima_copia=None):
    return r.armar(dias_periodo=dias_periodo, serie_larga=serie, inicio=inicio, hoy=hoy, fuente=fuente,
                   moneda="USD", nuevos=nuevos or {}, canales=canales or {}, cohortes=cohortes,
                   inicio_copia=inicio_copia, meta_roas=meta_roas, canal=canal, url_dia="/x/dia?tienda=",
                   ultima_copia=ultima_copia)


def test_por_dia_rellena_con_ceros():
    filas = [{"fecha": "2026-09-02", "ingresos": 10, "gasto": 4, "pedidos": 1}]
    assert r.por_dia("2026-09-01", "2026-09-03", filas) == [
        {"f": "2026-09-01", "ing": 0.0, "gas": 0.0, "ped": 0.0, "nc": 0.0},
        {"f": "2026-09-02", "ing": 10.0, "gas": 4.0, "ped": 1.0, "nc": 0.0},
        {"f": "2026-09-03", "ing": 0.0, "gas": 0.0, "ped": 0.0, "nc": 0.0}]


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
    # 4 semanas de 100 y luego: un día +50 %, uno −40 %, uno +30 %, uno +26 %, uno +10 % y hoy +300 %.
    base = [(100, 50, 1)] * 28
    periodo = [(150, 50, 1), (60, 50, 1), (130, 50, 1), (126, 50, 1), (110, 50, 1), (400, 50, 1)]
    raros = r.raros("ventas", _dias(base + periodo), inicio=28)
    assert raros == {0: pytest.approx(0.5), 1: pytest.approx(-0.4), 2: pytest.approx(0.3)}   # el +26 % no entra


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
    assert "10 % más" in frases[0]["texto"] and "1 USD en anuncios" in frases[0]["texto"]
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
    assert avisos and "5 % del gasto" in avisos[0]["texto"]
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
    assert frase.startswith("Por canal, según el Pixel: Meta, 89 % del gasto y 2,00× de retorno; Google Ads")
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
    assert ventas["variacion_texto"] == "100 %"
    assert len(out["datos"]["previos"]) == 6 and out["datos"]["comparar"] is True
    assert "6 días completos" in out["subtitulo"]


def test_armar_sin_datos_previos_no_compara(es):
    serie = _dias([(0, 0, 0)] * 6 + [(200, 50, 2)] * 7)
    out = _armar(serie, dias_periodo=7, inicio=6)
    assert out["datos"]["comparar"] is False and out["tarjetas"][0]["variacion"] is None


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
    assert out["tarjetas"][-1]["clave"] == "clientes_nuevos" and out["tarjetas"][-1]["texto"] == "50 %"
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
    assert d["stats"][0]["variacion_texto"] == "▲ 100 %" and d["stats"][0]["tono"] == "bueno"
    assert [c["nombre"] for c in d["canales"]] == ["Meta", "Google Ads"]
    assert d["anuncios"][0]["creatv"]["experimento_id"] == 7 and d["anuncios"][1]["nombre"] == "g1"
    assert d["anuncios"][1]["creatv"] is None and d["arrancaron"] == 3
    sin_antes = r.detalle_dia("2026-09-17", {"ing": 1, "gas": 1, "ped": 1}, None, {}, [], 0, {}, "USD", "tienda",
                              None, None)
    assert sin_antes["comparado"] is None and sin_antes["stats"][0]["variacion_texto"] == ""


def test_dia_semana_en_los_dos_idiomas():
    assert idiomas.dia_semana(date(2026, 9, 17), "es") == "jueves 17 de septiembre"
    assert idiomas.dia_semana(date(2026, 9, 17), "en") == "Thursday, September 17"
