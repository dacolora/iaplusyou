"""Evaluación gratis del contenido (spec 2026-09-28 §5): métricas, veredicto,
diagnóstico, resumen de la tienda, rastreo y alertas. Todo puro."""
import pytest

from triple_whale import evaluacion as ev

REGLAS = {"impresiones_min": 1000, "roas_min": 2.0, "ctr_min": 1.0, "thruplay_min": 0.15}


def anuncio(ad_id, gasto=100.0, impresiones=10000, clics=150, vistas_3s=3000, thruplays=900, pedidos=0.0,
            ingresos=0.0, canal="facebook-ads", utm_ok=True, **kw):
    t = {"canal": canal, "ad_id": ad_id, "anuncio": f"Anuncio {ad_id}", "campana": "C", "gasto": gasto,
         "impresiones": impresiones, "clics": clics, "clics_salida": 0, "vistas_3s": vistas_3s,
         "thruplays": thruplays, "pedidos": pedidos, "ingresos": ingresos, "utm_ok": utm_ok}
    t.update(kw)
    return t


def _por_id(resultado):
    return {a["ad_id"]: a for a in resultado["anuncios"]}


def test_metricas_derivadas():
    m = ev.metricas(anuncio("1", gasto=50, impresiones=2000, clics=40, vistas_3s=600, thruplays=150, pedidos=2,
                            ingresos=150, nc_ingresos=60))
    assert m["ctr"] == pytest.approx(2.0) and m["cpm"] == pytest.approx(25.0) and m["cpc"] == pytest.approx(1.25)
    assert m["gancho"] == pytest.approx(0.3) and m["retencion"] == pytest.approx(0.25)
    assert m["roas"] == pytest.approx(3.0) and m["cpa"] == pytest.approx(25.0) and m["ticket"] == pytest.approx(75.0)
    assert m["conversion"] == pytest.approx(0.05) and m["nc_roas"] == pytest.approx(1.2) and m["es_video"]
    vacio = ev.metricas({})
    assert vacio["ctr"] is None and vacio["roas"] is None and vacio["gancho"] is None and not vacio["es_video"]


def test_veredictos_con_ventas():
    r = ev.evaluar([
        anuncio("gana", pedidos=5, ingresos=400),                # ROAS 4 con 5 pedidos
        anuncio("pierde", gasto=200, pedidos=0, ingresos=0),     # gastó 2 ventas al CPA de la cuenta, ROAS 0
        anuncio("nuevo", impresiones=300, gasto=3),              # sin datos
        anuncio("tibio", gasto=20, pedidos=1, ingresos=30),      # ni fu ni fa
    ], reglas=REGLAS)
    a = _por_id(r)
    assert a["gana"]["veredicto"] == "ganador" and "4,0" in a["gana"]["motivo"]
    assert a["pierde"]["veredicto"] == "perdedor"
    assert a["nuevo"]["veredicto"] == "sin_datos"
    assert a["tibio"]["veredicto"] in ("en_prueba", "prometedor")
    assert r["hay_ventas"] and r["meta_roas"] == 2.0
    # Orden: ganadores primero, sin datos al final.
    assert r["anuncios"][0]["ad_id"] == "gana" and r["anuncios"][-1]["ad_id"] == "nuevo"
    assert r["conteo"]["ganador"] == 1 and r["conteo"]["perdedor"] == 1


def test_sin_ventas_en_la_cuenta_no_hay_ganadores_ni_perdedores():
    r = ev.evaluar([anuncio("1", gasto=500), anuncio("2", gasto=800, clics=400), anuncio("3")], reglas=REGLAS)
    assert not r["hay_ventas"]
    assert {a["veredicto"] for a in r["anuncios"]} <= {"prometedor", "en_prueba"}
    alertas = ev.alertas(r)
    assert alertas[0]["nivel"] == "alta" and "tw_source" in alertas[0]["texto"]


def test_meta_de_roas_apagada_usa_la_mediana_de_la_cuenta():
    lista = [anuncio(str(i), pedidos=4, ingresos=100 * (i + 1)) for i in range(5)]   # ROAS 1..5, mediana 3
    r = ev.evaluar(lista, reglas={"impresiones_min": 1000, "roas_min": None})
    assert r["meta_roas"] == pytest.approx(3.0)
    assert {a["ad_id"] for a in r["anuncios"] if a["veredicto"] == "ganador"} == {"2", "3", "4"}


def test_diagnostico_contra_la_mediana_de_la_cuenta():
    base = [anuncio(str(i)) for i in range(4)]   # gancho 0,30 · retención 0,30 · CTR 1,5 % · CPM 10
    malos = [
        anuncio("gancho", vistas_3s=1000, thruplays=300),          # gancho 0,10
        anuncio("retiene_poco", thruplays=300),                     # retención 0,10
        anuncio("sin_clic", clics=50),                              # CTR 0,5 %
        anuncio("caro", gasto=300),                                 # CPM 30
        anuncio("fuerte", vistas_3s=6000, thruplays=3000, clics=400),
        anuncio("sin_rastreo", utm_ok=False),
    ]
    a = _por_id(ev.evaluar(base + malos, reglas=REGLAS))
    assert "gancho_debil" in a["gancho"]["problemas"]
    assert "no_retiene" in a["retiene_poco"]["problemas"]
    assert "sin_clic" in a["sin_clic"]["problemas"]
    assert "caro" in a["caro"]["problemas"]
    assert {"gancho_fuerte", "retiene", "clic_fuerte"} <= set(a["fuerte"]["fortalezas"])
    assert a["fuerte"]["veredicto"] == "prometedor"
    assert "sin_rastreo" in a["sin_rastreo"]["problemas"]
    assert a["0"]["problemas"] == [] and a["0"]["fortalezas"] == []


def test_no_convierte_solo_con_clics_y_ventas_en_la_cuenta():
    lista = [anuncio(str(i), clics=200, pedidos=10, ingresos=600) for i in range(4)]   # conversión 5 %
    lista.append(anuncio("clic_sin_compra", clics=200, pedidos=1, ingresos=60))       # conversión 0,5 %
    a = _por_id(ev.evaluar(lista, reglas=REGLAS))
    assert "no_convierte" in a["clic_sin_compra"]["problemas"]


def test_fatiga_compara_los_ultimos_7_dias_con_los_7_anteriores():
    total = [anuncio("1", pedidos=10, ingresos=800), anuncio("2", pedidos=5, ingresos=400)]
    previos = [anuncio("1", pedidos=6, ingresos=600, gasto=100), anuncio("2", pedidos=3, ingresos=200, gasto=100)]
    recientes = [anuncio("1", pedidos=4, ingresos=200, gasto=100), anuncio("2", pedidos=3, ingresos=210, gasto=100)]
    r = ev.evaluar(total, recientes, previos, REGLAS)
    a = _por_id(r)
    assert a["1"]["fatiga"] and "fatiga" in a["1"]["problemas"]      # ROAS 6 → 2
    assert not a["2"]["fatiga"]
    assert any("cansando" in x["texto"] for x in ev.alertas(r))


def test_sin_suficientes_anuncios_comparables_usa_umbrales_absolutos():
    r = ev.evaluar([anuncio("solo", clics=50)], reglas=REGLAS)     # CTR 0,5 % < ctr_min 1 %
    assert r["benchmarks"]["ctr"] is None
    assert "sin_clic" in r["anuncios"][0]["problemas"]


def test_resumen_cuenta_reparte_el_gasto():
    r = ev.evaluar([anuncio("gana", pedidos=5, ingresos=400), anuncio("pierde", gasto=300),
                    anuncio("tt", canal="tiktok-ads", gasto=100, pedidos=1, ingresos=50)], reglas=REGLAS)
    c = r["cuenta"]
    assert c["m"]["gasto"] == 500 and c["m"]["pedidos"] == 6
    assert c["pct_gasto"]["perdedor"] == pytest.approx(0.6)
    assert [k["canal"] for k in c["canales"]] == ["facebook-ads", "tiktok-ads"]
    assert any("60" in x["texto"] and "perdedores" in x["texto"] for x in ev.alertas(r))


def test_resumen_tienda_con_variacion():
    actual = [{"gasto": 100, "ingresos": 500, "pedidos": 10, "nc_pedidos": 4, "nc_ingresos": 200}]
    previo = [{"gasto": 100, "ingresos": 800, "pedidos": 16}]
    t = ev.resumen_tienda(actual, previo)
    assert t["mer"] == pytest.approx(5.0) and t["ticket"] == pytest.approx(50.0) and t["pct_nuevos"] == pytest.approx(0.4)
    assert t["variacion"]["ingresos"] == pytest.approx(-0.375) and t["variacion"]["mer"] == pytest.approx(-0.375)
    assert ev.resumen_tienda([]) is None
    r = ev.evaluar([anuncio("1", pedidos=5, ingresos=400)], reglas=REGLAS)
    assert any("MER" in x["texto"] for x in ev.alertas(r, t))


def test_rastreo():
    r = ev.evaluar([anuncio("1", utm_ok=False, gasto=300), anuncio("2", gasto=100), anuncio("3", utm_ok=None),
                    anuncio("4", canal="google-ads", utm_ok=False)], reglas=REGLAS)
    info = ev.rastreo(r["anuncios"])
    assert info["sin_rastreo"] == 1 and info["anuncios"] == 2 and info["pct_gasto"] == pytest.approx(0.6)
    assert ev.rastreo([a for a in r["anuncios"] if a["utm_ok"] is None]) is None
    assert any("tw_source" not in x["texto"] and "parámetros" in x["texto"] for x in ev.alertas(r, None, info))


def test_alerta_de_ganadores():
    r = ev.evaluar([anuncio("1", pedidos=5, ingresos=400), anuncio("2", pedidos=5, ingresos=400)], reglas=REGLAS)
    assert ev.alertas(r)[-1] == {"nivel": "bien", "texto": "2 anuncios ganadores: úsalos como base para los próximos."}
